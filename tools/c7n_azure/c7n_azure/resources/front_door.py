# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.utils import type_schema
from c7n_azure.utils import ResourceIdParser
from c7n_azure.filters import Filter


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

@FrontDoor.filter_registry.register('frontdoor-waf-is-enabled')
class WebAppFirewallMissingFilter(Filter):
    """Frontdoor check waf enabled on front door profiles

    :example:

    .. code-block:: yaml

        policies:
            name: test-frontdoor-waf-is-enabled
            resource: azure.front-door
            filters: [
                - type: frontdoor-waf-is-enabled        
            ]

    """
    schema = type_schema('frontdoor-waf-is-enabled')
    
    def process(self, resources, event=None):
        client = self.manager.get_client()
        results = []
        for r in resources:
            for fes in r['properties']['frontendEndpoints']:
                fe = client.frontend_endpoints.get(r['resourceGroup'], r['name'],fes['name'])
                if fe.web_application_firewall_policy_link is None:
                    results.append(r)
        return results
    
@resources.register('frontdoor-waf')
class FrontDoorWAFResource(ArmResourceManager):
    """Resource Group Resource

    :example:

    Finds all FrontDoor WAF in the subscription.

    .. code-block:: yaml

        policies:
            - name: frontdoor_managed_rule_is_enabled
              resource: azure.frontdoor_waf
              filters: 
                - type: value
                  key: sku.name
                  op: in
                  value: ['Premium_AzureFrontDoor','Classic_AzureFrontDoor']
    """
  
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['ResourceType', 'Subscription']

        resource_type = 'Microsoft.Network/frontdoorWebApplicationFirewallPolicies' 
        
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resources', 'list', None)

@FrontDoorWAFResource.filter_registry.register('frontdoor-waf-managed-rule-is-enabled')
class WebAppFirewallManagedRuleEnabledFilter(Filter):
    """CDN check waf enabled on front door profiles

    :example:

    Returns all CDNs with Standard_Verizon sku

    .. code-block:: yaml

        policies:
            name: frontdoor-waf-managed-rule-is-enabled
            resource: azure.frontdoor-waf
            filters: 
                - type: value
                  key: type
                  op: eq
                  value: 'Microsoft.Network/frontdoorWebApplicationFirewallPolicies'
                - type: value
                  key: sku.name
                  op: in
                  value: ['Premium_AzureFrontDoor','Classic_AzureFrontDoor']    
                - type: 'frontdoor-waf-managed-rule-is-enabled',
                  group: JAVA 
                  id: 944240 
    """

    p_annotation_key = 'c7n:WAFRuleDisabled'
    schema = type_schema(
        'frontdoor-waf-managed-rule-is-enabled', **{
            'group': {'type': 'string'},
            'id': {'type': 'number'}}
    )
    
    def process(self, resources, event=None):
        session = self.manager.get_session()
        client = session.client('azure.mgmt.frontdoor.FrontDoorManagementClient')
        results = []
        for resource in resources:
                waf_policy_id = ResourceIdParser.get_resource_name(resource['id'])
                policy = client.policies.get(resource['resourceGroup'],waf_policy_id)
                for managedset in policy.managed_rules.managed_rule_sets:
                    for overrides in managedset.rule_group_overrides:
                        if (overrides.rule_group_name == self.data['group']):
                            for ja in overrides.rules:
                                if ja.rule_id == str(self.data['id']):
                                    if ja.enabled_state == 'Disabled':
                                        resource[self.p_annotation_key] = {'Disabled Rule Id':ja.rule_id}
                                        results.append(resource)
        return results