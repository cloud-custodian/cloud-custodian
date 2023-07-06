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


@FrontDoor.filter_registry.register('waf')
class WebAppFirewallFilter(Filter):
    """Frontdoor check waf enabled on front door profiles for Classic_AzureFrontDoor

    :example:

    .. code-block:: yaml

        policies:
          - name: test-frontdoor-waf
            resource: azure.front-door
            filters:
              - type: waf
                state: Disabled


    """
    schema = type_schema('waf',required=['state'],
            state={'type': 'string', 'enum': ['Enabled', 'Disabled']})

    def check_state(self, link):
        if self.data.get('state') == 'Disabled' and link is None:
            return True
        if self.data.get('state') == 'Enabled' and link is not None:
            return True

    def process(self, resources, event=None):
        client = self.manager.get_client()
        matched = []
        for front_door in resources:
            for front_endpoints in front_door['properties']['frontendEndpoints']:
                front_endpoint = client.frontend_endpoints.get(
                    front_door['resourceGroup'], front_door['name'],front_endpoints['name'])
                if self.check_state(front_endpoint.web_application_firewall_policy_link):
                    matched.append(front_door)
        return matched
