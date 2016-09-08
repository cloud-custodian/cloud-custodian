# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import logging

from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import (
    FilterRegistry, ValueFilter, DefaultVpcBase, AgeFilter, OPERATORS)

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import type_schema, local_session, chunks, snapshot_identifier

log = logging.getLogger('custodian.redshift')

filters = FilterRegistry('redshift.filters')
actions = ActionRegistry('redshift.actions')


@resources.register('redshift')
class Redshift(QueryResourceManager):

    resource_type = "aws.redshift.cluster"
    filter_registry = filters
    action_registry = actions


@filters.register('default-vpc')
class DefaultVpc(DefaultVpcBase):
    """ Matches if an redshift database is in the default vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, redshift):
        return (redshift.get('VpcId') and
                self.match(redshift.get('VpcId')) or False)


@filters.register('param')
class Parameter(ValueFilter):

    schema = type_schema('param', rinherit=ValueFilter.schema)
    group_params = ()

    def process(self, clusters, event=None):
        groups = {}
        for r in clusters:
            for pg in r['ClusterParameterGroups']:
                groups.setdefault(pg['ParameterGroupName'], []).append(
                    r['ClusterIdentifier'])

        def get_params(group_name):
            c = local_session(self.manager.session_factory).client('redshift')
            param_group = c.describe_cluster_parameters(
                ParameterGroupName=group_name)['Parameters']
            params = {}
            for p in param_group:
                v = p['ParameterValue']
                if v != 'default' and p['DataType'] in ('integer', 'boolean'):
                    # overkill..
                    v = json.loads(v)
                params[p['ParameterName']] = v
            return params

        with self.executor_factory(max_workers=3) as w:
            group_names = groups.keys()
            self.group_params = dict(
                zip(group_names, w.map(get_params, group_names)))
        return super(Parameter, self).process(clusters, event)

    def __call__(self, db):
        params = {}
        for pg in db['ClusterParameterGroups']:
            params.update(self.group_params[pg['ParameterGroupName']])
        return self.match(params)


@actions.register('delete')
class Delete(BaseAction):

    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'}})

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for db_set in chunks(clusters, size=5):
                futures.append(
                    w.submit(self.process_db_set, db_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting redshift set \n %s",
                        f.exception())

    def process_db_set(self, db_set):
        skip = self.data.get('skip-snapshot', False)
        c = local_session(self.manager.session_factory).client('redshift')
        for db in db_set:
            params = {'ClusterIdentifier': db['ClusterIdentifier']}
            if skip:
                params['SkipFinalClusterSnapshot'] = True
            else:
                params['FinalClusterSnapshotIdentifier'] = snapshot_identifier(
                    'Final', db['ClusterIdentifier'])
            c.delete_cluster(**params)


@actions.register('retention')
class RetentionWindow(BaseAction):

    date_attribute = 'AutomatedSnapshotRetentionPeriod'
    schema = type_schema(
        'retention',
        **{'days': {'type': 'number'}})

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_snapshot_retention,
                    cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception setting Redshift retention  \n %s",
                        f.exception())

    def process_snapshot_retention(self, cluster):
        current_retention = int(cluster.get(self.date_attribute, 0))
        new_retention = self.data['days']

        if current_retention < new_retention:
            self.set_retention_window(
                cluster,
                max(current_retention, new_retention))
            return cluster

    def set_retention_window(self, cluster, retention):
        c = local_session(self.manager.session_factory).client('redshift')
        c.modify_cluster(
            ClusterIdentifier=cluster['ClusterIdentifier'],
            AutomatedSnapshotRetentionPeriod=retention)


@actions.register('snapshot')
class Snapshot(BaseAction):

    schema = type_schema('snapshot')

    def process(self, clusters):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_cluster_snapshot,
                    cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception creating Redshift snapshot  \n %s",
                        f.exception())
        return clusters

    def process_cluster_snapshot(self, cluster):
        c = local_session(self.manager.session_factory).client('redshift')
        c.create_cluster_snapshot(
            SnapshotIdentifier=snapshot_identifier(
                'Backup',
                cluster['ClusterIdentifier']),
            ClusterIdentifier=cluster['ClusterIdentifier'])


@resources.register('redshift-snapshot')
class RedshiftSnapshot(QueryResourceManager):
    """Resource manager for Redshift snapshots.
    """

    class Meta(object):

        service = 'redshift'
        type = 'redshift-snapshot'
        enum_spec = ('describe_cluster_snapshots', 'Snapshots', None)
        name = id = 'SnapshotIdentifier'
        filter_name = None
        filter_type = None
        dimension = None
        date = 'SnapshotCreateTime'

    resource_type = Meta

    filter_registry = FilterRegistry('redshift-snapshot.filters')
    action_registry = ActionRegistry('redshift-snapshot.actions')


@RedshiftSnapshot.filter_registry.register('age')
class RedshiftSnapshotAge(AgeFilter):

    schema = type_schema(
        'age', days={'type': 'number'},
        op={'type': 'string', 'enum': OPERATORS.keys()})

    date_attribute = 'SnapshotCreateTime'


@RedshiftSnapshot.action_registry.register('delete')
class RedshiftSnapshotDelete(BaseAction):

    def process(self, snapshots):
        log.info("Deleting %d Redshift snapshots", len(snapshots))
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, snapshot_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting snapshot set \n %s",
                        f.exception())
        return snapshots

    def process_snapshot_set(self, snapshots_set):
        c = local_session(self.manager.session_factory).client('redshift')
        for s in snapshots_set:
            c.delete_cluster_snapshot(
                SnapshotIdentifier=s['SnapshotIdentifier'],
                SnapshotClusterIdentifier=s['ClusterIdentifier'])
