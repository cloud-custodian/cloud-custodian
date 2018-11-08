# Copyright 2017-2018 Capital One Services, LLC
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

from c7n.utils import type_schema

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('function')
class Function(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudfunctions'
        version = 'v1'
        component = 'projects.locations.functions'
        enum_spec = ('list', 'functions[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = "projects/{}/locations/-"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': (
                    'projects/{project_id}/locations/'
                    '{location_id}/functions/{function_name}').format(
                        **resource_info)})


@Function.action_registry.register('delete')
class Delete(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}
