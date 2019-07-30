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


class SetIamPolicy(MethodAction):
    """ Sets IAM policy. It works with bindings only.

        There are available following member types:
        - allUsers,
        - allAuthenticatedUsers,
        - user,
        - group,
        - domain,
        - serviceAccount.

        Example:

        .. code-block:: yaml

            policies:
              - name: gcp-set-iam-policy-common
                resource: gcp.<resource-name>
                actions:
                  - type: set-iam-policy
                    bindings:
                      - members:
                          - user:user1@test.com
                          - user:user2@test.com
                        role: roles/owner
                      - members:
                          - user:user3@gmail.com
                        role: roles/viewer
        """
    schema = type_schema('set-iam-policy',
                         required=['bindings', 'mode'],
                         **{
                             'bindings': {
                                 'type': 'array',
                                 'minItems': 1,
                                 'items': {'role': {'type': 'string'},
                                           'members': {'type': 'array',
                                                       'items': {
                                                           'type': 'string'},
                                                       'minItems': 1}}
                             },
                             'mode': {'type': 'string', 'enum': ['add', 'remove', 'update']}
                         })
    method_spec = {'op': 'setIamPolicy'}
    schema_alias = True

    def get_resource_params(self, model, resource):
        bindings = self.data['bindings']
        result = {'resource': resource['name'],
                  'body': {
                      'policy': {
                          'bindings': bindings
                      }}
                  }
        return result
