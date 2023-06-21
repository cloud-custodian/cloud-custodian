# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.filters import Filter
from c7n.utils import type_schema

@resources.register('front-door')
class FrontDoor(ArmResourceManager):
    """Azure Front Door Resource

    :example:

    This policy will find all Front Doors

    .. code-block:: yaml

        policies:
          - name: all-front-doors
            resource: azure.front-door
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.frontdoor'
        client = 'FrontDoorManagementClient'
        enum_spec = ('front_doors', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/frontDoors'

@FrontDoor.filter_registry.register('waf-not-enabled')
class WebAppFirewallMissingFilter(Filter):
    """Frontdoor check waf enabled on front door profiles for Classic_AzureFrontDoor

    :example:

    .. code-block:: yaml

        policies:
            name: test-frontdoor-waf-is-enabled
            resource: azure.front-door
            filters: [
                - type: frontdoor-waf-is-enabled        
            ]

    """
    schema = type_schema('waf-not-enabled')
    
    def process(self, resources, event=None):
        client = self.manager.get_client()
        results = []
        for frontDoors in resources:
            for frontendpoints in frontDoors['properties']['frontendEndpoints']:
                frontendpoint = client.frontend_endpoints.get(
                        frontDoors['resourceGroup'], frontDoors['name'],frontendpoints['name'])
                if frontendpoint.web_application_firewall_policy_link is None:
                    results.append(frontDoors)
        return results
