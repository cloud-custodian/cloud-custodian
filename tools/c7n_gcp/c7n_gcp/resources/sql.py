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

import re

from c7n.utils import type_schema
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('sql-instance')
class SqlInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sqladmin'
        version = 'v1beta4'
        component = 'instances'
        enum_spec = ('list', "items[]", None)
        scope = 'project'

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project'],
                        'instance': resource_info['name']})


class SqlInstanceAction(MethodAction):

    def get_resource_params(self, model, resource):
        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {'project': project, 'instance': instance}


@SqlInstance.action_registry.register('delete')
class SqlInstanceDelete(SqlInstanceAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    path_param_re = re.compile(
        '.*?/projects/(.*?)/instances/(.*)')


@SqlInstance.action_registry.register('stop')
class SqlInstanceStop(MethodAction):

    schema = type_schema('stop')
    method_spec = {'op': 'patch'}
    path_param_re = re.compile('.*?/projects/(.*?)/instances/(.*)')

    def get_resource_params(self, model, resource):
        project, instance = self.path_param_re.match(
            resource['selfLink']).groups()
        return {'project': project,
                'instance': instance,
                'body': {'settings': {'activationPolicy': 'NEVER'}}}
