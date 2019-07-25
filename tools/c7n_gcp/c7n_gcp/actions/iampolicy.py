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

from c7n.utils import type_schema
from c7n_gcp.actions import MethodAction


class SetIamPolicyBaseAction(MethodAction):

    schema = type_schema('set-iam-policy',
                         required=['bindings'],
                         **{
                             'bindings': {
                                 'type': 'array',
                                 'items': {'role': {'type': 'string'},
                                           'members': {'type': 'array',
                                                       'items': {
                                                           'type': 'string'}}}
                             }
                         }
                         )
    method_spec = {'op': 'setIamPolicy'}

    MEMBER_TYPES = ['allUsers', 'allAuthenticatedUsers',
                    'user', 'group', 'domain', 'serviceAccount']

    def get_resource_params(self, model, resource):
        result = {'resource': resource['name'],
                  'body': {
                      'policy': {
                          'bindings': []
                      }}
                  }
        bindings = result['body']['policy']['bindings']

        if self.data['bindings']:
            for binding in self.data['bindings']:
                if binding['role'] and binding['members']:
                    members = []
                    for member in binding['members']:
                        requires_update = True
                        for member_type in self.MEMBER_TYPES:
                            if member.startswith(member_type + ':'):
                                requires_update = False
                                break
                        if requires_update:
                            member = 'user:' + member
                        members.append(member)
                    bindings.append({'role': binding['role'], 'members': members})
        return result
