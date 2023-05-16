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
    """Azure Front Door Resource

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
    
    def _process_resource(self, resource, account_client, throughput):
        offer = resource['c7n:offer']
        new_offer = dict(offer)
        new_offer.pop('c7n:MatchedFilters', None)
        new_offer['content']['offerThroughput'] = throughput
        account_client.ReplaceOffer(offer['_self'], new_offer)

@FrontDoorCDN.filter_registry.register('frontdoor-waf-policy')
class WebAppFirewallFilter(Filter):
    p_annotation_key = 'c7n:WAFPolicy'
    p_missing_key = 'c7n:WAFPolicyMissing'
    schema = type_schema(
        'frontdoor-waf-policy'
    )
    
    def process(self, resources, event=None):
        client = self.manager.get_client()
        session = local_session(self.manager.session_factory)
        frontDoor_client = session.client('azure.mgmt.frontdoor.FrontDoorManagementClient')
        results = []
        for r in resources:
            if not r["sku"].get("name") == "Premium_AzureFrontDoor" or not r["properties"].get("resourceState") == "Active" or not r["properties"].get("provisioningState") =="Succeeded":
                continue
            policies = list(client.security_policies.list_by_profile(r["resourceGroup"],r["name"]))
            if not policies and self.data['key'] == 'missing':
                r[self.p_missing_key] = {'WAFPolicyMissing':r['name']}
                results.append(r)
            for ruleset in policies:
                waf_policy_id = ResourceIdParser.get_resource_name(ruleset.parameters.waf_policy.id)
                rules = frontDoor_client.policies.get(r["resourceGroup"],waf_policy_id)
                for managedset in rules.managed_rules.managed_rule_sets:
                    for overrides in managedset.rule_group_overrides:
                        if (overrides.rule_group_name == self.data['key']):
                            for ja in overrides.rules:
                                if ja.rule_id == str(self.data['name']) and ja.enabled_state == self.data['state']:
                                    r[self.p_annotation_key] = {'WAFPolicy':r['name']}
                                    results.append(r)

        return results
    
        