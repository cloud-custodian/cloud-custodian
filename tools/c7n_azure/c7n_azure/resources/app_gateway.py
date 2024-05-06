# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources

from c7n.filters import Filter
from c7n.utils import type_schema


@resources.register('application-gateway')
class ApplicationGateway(ArmResourceManager):
    """Azure Application Gateway

    :example:

    This policy will find all Application Gateways

    .. code-block:: yaml

        policies:
          - name: app_gateways
            resource: azure.application-gateway

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('application_gateways', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/applicationGateways'


@ApplicationGateway.filter_registry.register('waf')
class ApplicationGatewayWafFilter(Filter):
    """
    Filter Application Gateways using WAF rule configuration.
    State is defaulted to 'disabled'.

    WAF rule group with rule ids can be found here:
    https://learn.microsoft.com/en-us/azure/web-application-firewall/ag/application-gateway-crs-rulegroups-rules?tabs=owasp32#general-32

    :example:

    Return all the App Gateways which have rule '944240' disabled.

    .. code-block:: yaml

        policies:
          - name: test-app-gateway
            resource: azure.application-gateway
            filters:
              - type: waf
                override_rule: 944240
    """

    schema = type_schema(
        'waf',
        required=[],
        **{
            'override_rule': {'type': 'number'},
            'state': {'type': 'string', 'enum': ['enabled', 'disabled']}}
    )

    def process(self, resources, event=None):

        filter_override_rule = self.data.get('override_rule')
        filter_state = self.data.get('state', 'disabled')

        client = self.manager.get_client()
        app_gate_wafs = list(client.web_application_firewall_policies.list_all())
        result = []

        for resource in resources:
            if 'webApplicationFirewallConfiguration' in resource['properties']:
                # If WAF configuration is part of the Application
                # Gateway resource.
                if filter_override_rule is None and filter_state == 'enabled':
                    result.append(resource)
                    continue
                for disabled_rule_Group in resource['properties'][
                        'webApplicationFirewallConfiguration']['disabledRuleGroups']:
                    if filter_override_rule in disabled_rule_Group['rules'] \
                        and filter_state == 'disabled':
                        result.append(resource)
                    elif filter_override_rule not in disabled_rule_Group['rules'] \
                        and filter_state == 'enabled':
                        result.append(resource)
            elif 'firewallPolicy' in resource['properties']:
                # If WAF is configured as a separate resource and
                # associated with the Application Gateway.
                if filter_override_rule is None and filter_state == 'enabled':
                    result.append(resource)
                    continue
                waf_policy_name = resource['properties']['firewallPolicy']['id']
                for app_gate_waf in app_gate_wafs:
                    if app_gate_waf.id != waf_policy_name:
                        continue

                    app_gate_waf = app_gate_waf.serialize(True).get('properties', {})
                    for rule_set in app_gate_waf.get('managedRules').get('managedRuleSets'):
                        for group in rule_set.get('ruleGroupOverrides'):
                            for rule in group.get('rules'):
                                if filter_override_rule == int(rule.get('ruleId')) \
                                    and filter_state.lower() == rule.get('state').lower():
                                    result.append(resource)
            else:
                # Application Gateway without any WAF configured
                if filter_state == 'disabled':
                    result.append(resource)

        return result
