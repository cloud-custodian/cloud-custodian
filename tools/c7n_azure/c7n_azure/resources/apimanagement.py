# Copyright 2019 Microsoft Corporation
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
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from azure.mgmt.resource.resources.models import GenericResource

from c7n.utils import type_schema


@resources.register('api-management')
class ApiManagement(ArmResourceManager):
    """API Management Resource

    :example:

    .. code-block:: yaml

        policies:
          - name: api-management-no-vnet
            resource: azure.api-management
            filters:
              - type: value
                key: properties.virtualNetworkType
                op: eq
                value: None

    """

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.apimanagement'
        client = 'ApiManagementClient'
        enum_spec = ('api_management_service', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.ApiManagement/service'


@ApiManagement.action_registry.register('resize')
class Resize(AzureBaseAction):
    """
    Action to scale api management resource.
    Required arguments: capacity in units and tier (Developer, Basic, Standard or Premium).

    :example:
    This policy will resize api management to Premium tier with 8 units.

    .. code-block:: yaml

        policies:
          - name: resize-api
            resource: azure.api-management
            filters:
              - type: value
                key: name
                value: test-api
            actions:
              - type: resize
                tier: Premium
                capacity: 8

    """

    schema = type_schema(
        'resize',
        required=['capacity', 'tier'],
        **{
            'capacity': {'type': 'number'},
            'tier': {'enum': ['Developer', 'Basic', 'Standard', 'Premium']}
        })

    def __init__(self, data, manager=None):
        super(Resize, self).__init__(data, manager)
        self.capacity = self.data['capacity']
        self.tier = self.data['tier']

    def _prepare_processing(self):
        self.client = self.session.client('azure.mgmt.resource.ResourceManagementClient')

    def _process_resource(self, resource):
        resource['sku']['capacity'] = self.capacity
        resource['sku']['tier'] = self.tier
        resource['sku']['name'] = self.tier

        az_resource = GenericResource.deserialize(resource)

        api_version = self.session.resource_api_version(resource['id'])

        # create a GenericResource object with the required parameters
        generic_resource = GenericResource(sku=az_resource.sku)

        self.client.resources.update_by_id(resource['id'], api_version, generic_resource)
