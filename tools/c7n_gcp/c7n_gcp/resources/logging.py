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
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

# TODO .. folder, billing account, org sink
# how to map them given a project level root entity sans use of c7n-org


@resources.register('logsink')
class LogSink(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'logging'
        version = 'v1'
        component = 'projects.sinks'
        enum_spec = ('list', 'sinks[]', None)
        scope_key = 'parent'
        scope_template = "projects/{}/sinks"
        id = "name"

        @staticmethod
        def get(client, resource_info):
            return client.get('get', {
                'sinkName': 'projects/{project_id}/sinks/{name}'.format(
                    **resource_info)})
