# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
        doc_groups = ['Integration']

        service = 'azure.mgmt.apimanagement'
        client = 'ApiManagementClient'
        enum_spec = ('api_management_service', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.[name, capacity]'
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
