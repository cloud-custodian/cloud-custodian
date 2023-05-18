# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.utils import local_session, type_schema
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

@resources.register('frontdoor-cdn')
class FrontDoorCDN(ArmResourceManager):
    """Azure CDN Front Door Resource

    :example:

    This policy will find all Front Doors

    .. code-block:: yaml

        policies:
          - name: all-front-doors
            resource: azure.front-door
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Media']

        service = 'azure.mgmt.cdn'
        client = 'CdnManagementClient'
        enum_spec = ('profiles', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name',
        )
        resource_type = 'Microsoft.Cdn/profiles'
    

@FrontDoorCDN.filter_registry.register('frontdoor-waf-is-enabled')
class WebAppFirewallMissingFilter(Filter):
    schema = type_schema(
        'frontdoor-waf-is-enabled'
    )
    
    def process(self, resources, event=None):
        client = self.manager.get_client()
        results = []
        for r in resources:
            if not r["properties"].get("resourceState") == "Active" or not r["properties"].get("provisioningState") =="Succeeded":
                if not r["sku"].get("name") == "Premium_AzureFrontDoor" and not r["sku"].get("name") == "Standard_AzureFrontDoor" and not r["sku"].get("name") == "Classic_AzureFrontDoor":
                    continue
            policies = list(client.security_policies.list_by_profile(r["resourceGroup"],r["name"]))
            if not policies:
                results.append(r)
        return results

@resources.register('frontdoor-waf')
class FrontDoorWAF(ArmResourceManager):
    """Azure Front Door Web Application Firewall Resource

    :example:

    This policy will find all Front Door Web Application Firewalls

    .. code-block:: yaml

        policies:
          - name: frontdoor-waf
            resource: azure.frontdoor-waf
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Resource Group', 'Subscription']

        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resources', 'list', None)

        default_report_fields = (
            'name',
            'location',
        )
        resource_type = 'resources'

@FrontDoorWAF.filter_registry.register('frontdoor-waf-managed-rule-is-enabled')
class WebAppFirewallManagedRuleEnabledFilter(Filter):
    resource_type_name = 'Microsoft.Network/frontdoorWebApplicationFirewallPolicies'
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
            if resource['type'] == self.resource_type_name:
                if not resource["sku"].get("name") == "Premium_AzureFrontDoor" and not resource["sku"].get("name") == "Classic_AzureFrontDoor":
                    continue
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
    
        