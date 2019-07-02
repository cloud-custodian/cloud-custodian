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
import re

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

from c7n.utils import type_schema


@resources.register('dm-deployment')
class DMDeployment(QueryResourceManager):
    """GCP resource: https://cloud.google.com/deployment-manager/docs/reference/latest/deployments
    """
    class resource_type(TypeInfo):
        service = 'deploymentmanager'
        version = 'v2'
        component = 'deployments'
        enum_spec = ('list', 'deployments[]', None)
        id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'deployment': resource_info['name']})


@DMDeployment.action_registry.register('delete')
class DeleteInstanceGroupManager(MethodAction):
    """Deletes a deployment

    :Example:

    .. code-block:: yaml
        policies:
          - name: delete-deployments
            description: Delete all deployments
            resource: gcp.dm-deployment
            filters:
              - type: value
                key: name
                op: eq
                value: test-deployment
            actions:
              - delete

    https://cloud.google.com/deployment-manager/docs/reference/latest/deployments/delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    path_param_re = re.compile('.*?/projects/(.*?)/global/deployments/(.*)')

    def get_resource_params(self, m, r):
        project, name = self.path_param_re.match(r['selfLink']).groups()
        return {'project': project, 'deployment': name}
