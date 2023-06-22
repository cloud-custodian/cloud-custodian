# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.filters import Filter
from c7n.utils import type_schema
from c7n_azure.utils import ResourceIdParser


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
            name: test-frontdoor-waf
            resource: azure.front-door
            filters:
              - type: waf
                state: disabled


    """
    schema = type_schema('waf',required=['state'],
            state={'type': 'string', 'enum': ['None', 'not None']})

    def check_state(self, link):
        if self.data.get('state') == 'disabled' and link is None:
            return True
        if self.data.get('state') == 'enabled' and link is not None:
            return True
        return False

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
    
@FrontDoor.filter_registry.register('waf-managed-rule')
class WebAppFirewallFilter(Filter):
    """Frontdoor check waf managed rule enabled/disabled

    :example:

    .. code-block:: yaml

        policies:
            name: test-frontdoor-waf-rule
            resource: azure.front-door
            filters:
                - and
                    - type: waf
                      state: Enabled
                    - type: waf-managed-rule
                      group: JAVA 
                      id: 944240 
                      state: Disabled
    
    """
    schema = type_schema('waf-managed-rule',required=['state'],
            state={'type': 'string', 'enum': ['None', 'not None']})

    def check_state(self, link):
        if self.data.get('state') == 'Disabled' and link is None:
            return True
        if self.data.get('state') == 'Enabled' and link is not None:
            return True
        return False

    def process(self, resources, event=None):
        client = self.manager.get_client()
        matched = []
        for front_door in resources:
            for front_endpoints in front_door['properties']['frontendEndpoints']:
                front_endpoint = client.frontend_endpoints.get(
                    front_door['resourceGroup'], front_door['name'],front_endpoints['name'])
                waf_policy_name = ResourceIdParser.get_resource_name(
                    front_endpoint.web_application_firewall_policy_link.id)
                policy = client.policies.get(front_door['resourceGroup'],waf_policy_name)
                for managed_set in policy.managed_rules.managed_rule_sets:
                    for overrides in managed_set.rule_group_overrides:
                        if (overrides.rule_group_name == self.data['group']):
                            for group in overrides.rules:
                                if group.enabled_state == self.data['state']:
                                        matched.append(front_door)
        return matched