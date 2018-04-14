# Copyright 2016-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import functools

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, AgeFilter, OPERATORS
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n import tags
from c7n.utils import (
    type_schema, local_session, snapshot_identifier, chunks,
    get_retry, generate_arn)

log = logging.getLogger('custodian.rds-cluster')

filters = FilterRegistry('rds-cluster.filters')
actions = ActionRegistry('rds-cluster.actions')

filters.register('tag-count', tags.TagCountFilter)
filters.register('marked-for-op', tags.TagActionFilter)


@resources.register('rds-cluster')
class RDSCluster(QueryResourceManager):
    """Resource manager for RDS clusters.
    """

    class resource_type(object):

        service = 'rds'
        type = 'cluster'
        enum_spec = ('describe_db_clusters', 'DBClusters', None)
        name = id = 'DBClusterIdentifier'
        filter_name = None
        filter_type = None
        dimension = 'DBClusterIdentifier'
        date = None

    filter_registry = filters
    action_registry = actions
    retry = staticmethod(get_retry(('Throttled',)))

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn, 'rds', region=self.config.region,
                account_id=self.account_id,
                resource_type=self.resource_type.type, separator=':')
        return self._generate_arn

    def augment(self, dbs):
        filter(None, _rds_cluster_tags(
            self.get_model(),
            dbs, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return dbs


def _rds_cluster_tags(model, dbs, session_factory, executor_factory, generator, retry):
    """Augment rds clusters with their respective tags."""

    def process_tags(db):
        client = local_session(session_factory).client('rds')
        arn = generator(db[model.id])
        tag_list = None
        try:
            tag_list = retry(client.list_tags_for_resource, ResourceName=arn)['TagList']
        except ClientError as e:
            if e.response['Error']['Code'] != 'DBClusterNotFoundFault':
                log.warning("Exception getting rdscluster tags\n %s", e)
            return None
        db['Tags'] = tag_list or []
        return db

    # Rds maintains a low api call limit, so this can take some time :-(
    with executor_factory(max_workers=1) as w:
        return list(w.map(process_tags, dbs))


@actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):
    """Mark a RDS cluster for specific custodian action

    :example:

    .. code-block:: yaml

            policies:
              - name: mark-for-delete
                resource: rds-cluster
                filters:
                  - type: default-vpc
                actions:
                  - type: mark-for-op
                    op: delete
                    days: 7
    """
    schema = type_schema(
        'mark-for-op', rinherit=tags.TagDelayedAction.schema)
    permissions = ('rds:AddTagsToResource',)

    batch_size = 5

    def process(self, dbs):
        return super(TagDelayedAction, self).process(dbs)

    def process_resource_set(self, dbs, tags):
        client = local_session(self.manager.session_factory).client('rds')
        for db in dbs:
            arn = self.manager.generate_arn(db['DBClusterIdentifier'])
            client.add_tags_to_resource(ResourceName=arn, Tags=tags)


@actions.register('tag')
@actions.register('mark')
class Tag(tags.Tag):
    """Mark/tag a RDS cluster with a key/value

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-owner-tag
                resource: rds-cluster
                filters:
                  - "tag:OwnerName": absent
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """

    concurrency = 2
    batch_size = 5
    permissions = ('rds:AddTagsToResource',)

    def process_resource_set(self, dbs, ts):
        client = local_session(
            self.manager.session_factory).client('rds')
        for db in dbs:
            arn = self.manager.generate_arn(db['DBClusterIdentifier'])
            client.add_tags_to_resource(ResourceName=arn, Tags=ts)


@actions.register('remove-tag')
@actions.register('unmark')
class RemoveTag(tags.RemoveTag):
    """Removes a tag or set of tags from RDS clusters

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-unmark-cluster
                resource: rds-cluster
                filters:
                  - "tag:ExpiredTag": present
                actions:
                  - type: unmark
                    tags: ["ExpiredTag"]
    """

    concurrency = 2
    batch_size = 5
    permissions = ('rds:RemoveTagsFromResource',)

    def process_resource_set(self, dbs, tag_keys):
        client = local_session(
            self.manager.session_factory).client('rds')
        for db in dbs:
            arn = self.manager.generate_arn(db['DBClusterIdentifier'])
            client.remove_tags_from_resource(
                ResourceName=arn, TagKeys=tag_keys)


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcSecurityGroups[].VpcSecurityGroupId"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = ""

    def get_permissions(self):
        return self.manager.get_resource_manager(
            'rds-subnet-group').get_permissions()

    def get_related_ids(self, resources):
        group_ids = set()
        for r in resources:
            group_ids.update(
                [s['SubnetIdentifier'] for s in
                 self.groups[r['DBSubnetGroup']]['Subnets']])
        return group_ids

    def process(self, resources, event=None):
        self.groups = {
            r['DBSubnetGroupName']: r for r in
            self.manager.get_resource_manager('rds-subnet-group').resources()}
        return super(SubnetFilter, self).process(resources, event)


filters.register('network-location', net_filters.NetworkLocation)


@actions.register('delete')
class Delete(BaseAction):
    """Action to delete a RDS cluster

    To prevent unwanted deletion of clusters, it is recommended to apply a
    filter to the rule

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-delete-unused
                resource: rds-cluster
                filters:
                  - type: metrics
                    name: CPUUtilization
                    days: 21
                    value: 1.0
                    op: le
                actions:
                  - type: delete
                    skip-snapshot: false
                    delete-instances: true
    """

    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'},
                     'delete-instances': {'type': 'boolean'}})

    permissions = ('rds:DeleteDBCluster',)

    def process(self, clusters):
        skip = self.data.get('skip-snapshot', False)
        delete_instances = self.data.get('delete-instances', True)
        client = local_session(self.manager.session_factory).client('rds')

        for cluster in clusters:
            if delete_instances:
                for instance in cluster.get('DBClusterMembers', []):
                    client.delete_db_instance(
                        DBInstanceIdentifier=instance['DBInstanceIdentifier'],
                        SkipFinalSnapshot=True)
                    self.log.info(
                        'Deleted RDS instance: %s',
                        instance['DBInstanceIdentifier'])

            params = {'DBClusterIdentifier': cluster['DBClusterIdentifier']}
            if skip:
                params['SkipFinalSnapshot'] = True
            else:
                params['FinalDBSnapshotIdentifier'] = snapshot_identifier(
                    'Final', cluster['DBClusterIdentifier'])
            try:
                client.delete_db_cluster(**params)
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidDBClusterStateFault':
                    self.log.info(
                        'RDS cluster in invalid state: %s',
                        cluster['DBClusterIdentifier'])
                    continue
                raise

            self.log.info(
                'Deleted RDS cluster: %s',
                cluster['DBClusterIdentifier'])


@actions.register('retention')
class RetentionWindow(BaseAction):
    """
    Action to set the retention period on rds cluster snapshots,
    enforce (min, max, exact) sets retention days occordingly.

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-backup-retention
                resource: rds-cluster
                filters:
                  - type: value
                    key: BackupRetentionPeriod
                    value: 21
                    op: ne
                actions:
                  - type: retention
                    days: 21
                    enforce: min
    """

    date_attribute = "BackupRetentionPeriod"
    # Tag copy not yet available for Aurora:
    #   https://forums.aws.amazon.com/thread.jspa?threadID=225812
    schema = type_schema(
        'retention', **{'days': {'type': 'number'},
                        'enforce': {'type': 'string', 'enum': [
                            'min', 'max', 'exact']}})
    permissions = ('rds:ModifyDBCluster',)

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
                        "Exception setting RDS cluster retention  \n %s",
                        f.exception())

    def process_snapshot_retention(self, cluster):
        current_retention = int(cluster.get('BackupRetentionPeriod', 0))
        new_retention = self.data['days']
        retention_type = self.data.get('enforce', 'min').lower()

        if retention_type == 'min':
            self.set_retention_window(
                cluster,
                max(current_retention, new_retention))
            return cluster

        if retention_type == 'max':
            self.set_retention_window(
                cluster,
                min(current_retention, new_retention))
            return cluster

        if retention_type == 'exact':
            self.set_retention_window(cluster, new_retention)
            return cluster

    def set_retention_window(self, cluster, retention):
        c = local_session(self.manager.session_factory).client('rds')
        c.modify_db_cluster(
            DBClusterIdentifier=cluster['DBClusterIdentifier'],
            BackupRetentionPeriod=retention,
            PreferredBackupWindow=cluster['PreferredBackupWindow'],
            PreferredMaintenanceWindow=cluster['PreferredMaintenanceWindow'])


@actions.register('snapshot')
class Snapshot(BaseAction):
    """Action to create a snapshot of a rds cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-snapshot
                resource: rds-cluster
                actions:
                  - snapshot
    """

    schema = type_schema('snapshot')
    permissions = ('rds:CreateDBClusterSnapshot',)

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
                        "Exception creating RDS cluster snapshot  \n %s",
                        f.exception())
        return clusters

    def process_cluster_snapshot(self, cluster):
        c = local_session(self.manager.session_factory).client('rds')
        c.create_db_cluster_snapshot(
            DBClusterSnapshotIdentifier=snapshot_identifier(
                'Backup',
                cluster['DBClusterIdentifier']),
            DBClusterIdentifier=cluster['DBClusterIdentifier'])


@resources.register('rds-cluster-snapshot')
class RDSClusterSnapshot(QueryResourceManager):
    """Resource manager for RDS cluster snapshots.
    """

    class resource_type(object):

        service = 'rds'
        type = 'rds-cluster-snapshot'
        enum_spec = (
            'describe_db_cluster_snapshots', 'DBClusterSnapshots', None)
        name = id = 'DBClusterSnapshotIdentifier'
        filter_name = None
        filter_type = None
        dimension = None
        date = 'SnapshotCreateTime'

    filter_registry = FilterRegistry('rdscluster-snapshot.filters')
    action_registry = ActionRegistry('rdscluster-snapshot.actions')


@RDSClusterSnapshot.filter_registry.register('age')
class RDSSnapshotAge(AgeFilter):
    """Filters rds cluster snapshots based on age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-snapshots-expired
                resource: rds-cluster-snapshot
                filters:
                  - type: age
                    days: 30
                    op: gt
    """

    schema = type_schema(
        'age', days={'type': 'number'},
        op={'type': 'string', 'enum': list(OPERATORS.keys())})

    date_attribute = 'SnapshotCreateTime'


@RDSClusterSnapshot.action_registry.register('delete')
class RDSClusterSnapshotDelete(BaseAction):
    """Action to delete rds cluster snapshots

    To prevent unwanted deletion of rds cluster snapshots, it is recommended
    to apply a filter to the rule

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-snapshots-expired-delete
                resource: rds-cluster-snapshot
                filters:
                  - type: age
                    days: 30
                    op: gt
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('rds:DeleteDBClusterSnapshot',)

    def process(self, snapshots):
        log.info("Deleting %d RDS cluster snapshots", len(snapshots))
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
        c = local_session(self.manager.session_factory).client('rds')
        for s in snapshots_set:
            c.delete_db_cluster_snapshot(
                DBClusterSnapshotIdentifier=s['DBClusterSnapshotIdentifier'])
