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
from datetime import datetime

from c7n.manager import resources
from c7n.actions import ActionRegistry, BaseAction
from c7n.query import QueryResourceManager
from c7n import utils
from c7n.utils import (
    local_session, type_schema, get_account_id,
    get_retry, chunks, generate_arn, snapshot_identifier)

actions = ActionRegistry('emr.actions')


@resources.register('emr')
class EMRCluster(QueryResourceManager):

    action_registry = actions

    def __init__(self, ctx, data):
        super(EMRCluster, self).__init__(ctx, data)
        self.queries = QueryFilter.parse(self.data.get('query', []))

    class Meta(object):
        service = 'emr'
        type = 'emr'
        enum_spec = ('list_clusters', 'Clusters', None)
        name = 'Name'
        id = 'Id'
        dimension = 'ClusterId'

    resource_type = Meta

    def resources(self, query=None):
        q = self.consolidate_query_filter()
        if q is not None:
            query = query or {}
            for i in range(0, len(q)):
                query[q[i]['Name']] = q[i]['Values']
        return super(EMRCluster, self).resources(query=query)

    def consolidate_query_filter(self):
        result = []
        names = set()
        # allow same name to be specified multiple times and append the queries
        # under the same name
        for q in self.queries:
            query_filter = q.query()
            if query_filter['Name'] in names:
                for filt in result:
                    if query_filter['Name'] == filt['Name']:
                        filt['Values'].extend(query_filter['Values'])
            else:
                names.add(query_filter['Name'])
                result.append(query_filter)
        return result

    def augment(self, resources):
        # remap for cwmetrics
        for r in resources:
            r['ClusterId'] = r['Id']
        return resources


@actions.register('terminate')
class Terminate(BaseAction):

    schema = type_schema('terminate')

    def process(self, emrs):

        client = local_session(self.manager.session_factory).client('emr')
        cluster_ids = []
        for emr in emrs:
            cluster_ids.append(emr['ClusterId'])
        try:
            client.terminate_job_flows(JobFlowIds=cluster_ids)
        except ClientError as e:
            raise

        self.log.info("Deleted emrs: %s", cluster_ids)
        return emrs


# Valid EMR Query Filters
EMR_VALID_FILTERS = {
    'CreatedAfter': datetime,
    'CreatedBefore': datetime,
    'ClusterStates': (
        'terminated',
        'bootstrapping',
        'running',
        'waiting',
        'terminating',
        'terminated',
        'terminated_with_errors')}


class QueryFilter(object):

    @classmethod
    def parse(cls, data):
        results = []
        for d in data:
            if not isinstance(d, dict):
                raise ValueError(
                    "EMR Query Filter Invalid structure %s" % d)
            results.append(cls(d).validate())
        return results

    def __init__(self, data):
        self.data = data
        self.key = None
        self.value = None

    def validate(self):
        if not len(self.data.keys()) == 1:
            raise ValueError(
                "EMR Query Filter Invalid %s" % self.data)
        self.key = self.data.keys()[0]
        self.value = self.data.values()[0]

        if self.key not in EMR_VALID_FILTERS and not self.key.startswith(
                'tag:'):
            raise ValueError(
                "EMR Query Filter invalid filter name %s" % (self.data))

        if self.value is None:
            raise ValueError(
                "EMR Query Filters must have a value, use tag-key"
                " w/ tag name as value for tag present checks"
                " %s" % self.data)
        return self

    def query(self):
        value = self.value
        if isinstance(self.value, basestring):
            value = [self.value]

        return {'Name': self.key, 'Values': value}

