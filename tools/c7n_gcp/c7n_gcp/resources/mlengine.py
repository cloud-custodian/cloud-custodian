# Copyright 2019 Capital One Services, LLC
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

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('ml-model')
class MLModel(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ml'
        version = 'v1'
        component = 'projects.models'
        enum_spec = ('list', 'models[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'name': 'projects/{}/models/{}'.format(
                    resource_info['project_id'],
                    resource_info['name'].rsplit('/', 1)[-1])})


@resources.register('ml-job')
class MLJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ml'
        version = 'v1'
        component = 'projects.jobs'
        enum_spec = ('list', 'jobs[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        id = 'jobId'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'name': 'projects/{}/jobs/{}'.format(
                    resource_info['project_id'],
                    resource_info['name'].rsplit('/', 1)[-1])})
