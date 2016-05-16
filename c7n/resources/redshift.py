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
import itertools

from concurrent.futures import as_completed
from datetime import datetime

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, ValueFilter

from c7n.manager import ResourceManager, resources
from c7n.utils import type_schema, local_session, chunks

log = logging.getLogger('custodian.redshift')

filters = FilterRegistry('redshift.filters')
actions = ActionRegistry('redshift.actions')


@resources.register('redshift')
class Redshift(ResourceManager):

    filter_registry = filters
    action_registry = actions

    def get_resources(self, resource_ids):
        c = local_session(self.session_factory).client('redshift')
        results = []
        for rid in resource_ids:
            results.extend(
                c.describe_clusters(ClusterIdentifier=rid)['Clusters'])
        return results

    def resources(self):
        c = local_session(self.session_factory).client('redshift')
        if self._cache.load():
            dbs = self._cache.get(
                {'region': self.config.region, 'resource': 'redshift'})
            if dbs is not None:
                return self.filter_resources(dbs)
        self.log.info('Querying redshift dbs')
        p = c.get_paginator('describe_clusters')
        results = p.paginate()
        snapshots = list(itertools.chain(*[rp['Clusters'] for rp in results]))
        self._cache.save(
            {'region': self.config.region, 'resource': 'redshift'}, snapshots)
        return self.filter_resources(snapshots)


@filters.register('param')
class Parameter(ValueFilter):

    schema = type_schema('param', rinherit=ValueFilter.schema)
    group_params = ()

    def process(self, resources, event=None):
        groups = {}
        for r in resources:
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
        return super(Parameter, self).process(resources, event)

    def __call__(self, db):
        params = {}
        for pg in db['ClusterParameterGroups']:
            params.update(self.group_params[pg['ParameterGroupName']])
        print params['require_ssl'], self.data['key'], self.data['value']
        return self.match(params)


@actions.register('delete')
class Delete(BaseAction):

    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'}})

    def process(self, resources):
        self.skip = self.data.get('skip-snapshot', False)
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for db_set in chunks(resources, size=5):
                futures.append(
                    w.submit(self.process_db_set, db_set))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception deleting redshift set \n %s" % (
                                f.exception()))

    def process_db_set(self, db_set):
        c = local_session(self.session_factory).client('redshift')
        now = datetime.now()
        for db in db_set:
            params = {'ClusterIdentifier': db['ClusterIdentifier']}
            if self.skip:
                params['SkipFinalClusterSnapshot'] = True
            else:
                params['FinalClusterSnapshotIdentifier'] = "%s-%s" % (
                    "%s-%s" % (now.strftime("%Y-%m-%d"),
                               db['ClusterIdentifier']))
            c.delete_cluster(**params)
