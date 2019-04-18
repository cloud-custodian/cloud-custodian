# Copyright 2018 Capital One Services, LLC
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
import jmespath

from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.provider import resources


@resources.register('bq-dataset')
class DataSet(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'bigquery'
        version = 'v2'
        component = 'datasets'
        enum_spec = ('list', 'datasets[]', None)
        scope = 'project'
        scope_key = 'projectId'
        get_requires_event = True
        id = "id"

        @staticmethod
        def get(client, event):
            # dataset creation doesn't include data set name in resource name.
            _, method = event['protoPayload']['methodName'].split('.')
            if method not in ('insert', 'update'):
                raise RuntimeError("unknown event %s" % event)
            expr = 'protoPayload.serviceData.dataset{}Response.resource.datasetName'.format(
                method.capitalize())
            ref = jmespath.search(expr, event)
            return client.execute_query('get', verb_arguments=ref)

    def augment(self, resources):
        client = self.get_client()
        results = []
        for r in resources:
            ref = r['datasetReference']
            results.append(
                client.execute_query(
                    'get', verb_arguments=ref))
        return results


@resources.register('bq-job')
class BigQueryJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'bigquery'
        version = 'v2'
        component = 'jobs'
        enum_spec = ('list', 'jobs[]', {'allUsers': True})
        scope = 'project'
        scope_key = 'projectId'
        id = 'id'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {
                'projectId': resource_info['project_id'],
                'jobId': resource_info['job_id']
            })


@resources.register('bq-project')
class BigQueryProject(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'bigquery'
        version = 'v2'
        component = 'projects'
        enum_spec = ('list', 'projects[]', None)
        scope = 'global'
        id = 'id'
