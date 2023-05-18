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


@ApplicationGateway.filter_registry.register('web-application-firewall')
class ApplicationGatewayWafFilter(Filter):
    """
    Filter Application Gateways using WAF rule configuration

    :example:

    Return all the App Gateways which have rule '944240' disabled.

    .. code-block:: yaml

        policies:
          - name: test-app-gateway
            resource: azure.application-gateway
            filters:
              - type: web-application-firewall
                override_rule: 944240
                state: disabled
    """

    schema = type_schema(
        'web-application-firewall',
        required=['override_rule', 'state'],
        override_rule = {'type': 'string'},
        state =  {'type': 'string', 'enum': ['disabled']}
    )

    def process(self, resources, event=None):

        filter_override_rule = self.data.get('override_rule')
        filter_state = self.data.get('state')

        client = self.manager.get_client()
        result = []

        for resource in resources:
            if 'firewallPolicy' in resource['properties']:
                waf_policy_name = resource['properties']['firewallPolicy']['id'].split('/')[-1]

                app_gate_waf = client.web_application_firewall_policies.\
                    get(resource['resourceGroup'],waf_policy_name)

                for rule_set in app_gate_waf.managed_rules.managed_rule_sets:
                    for group in rule_set.rule_group_overrides:
                        for rule in group.rules:
                            if filter_override_rule == rule.rule_id \
                                and filter_state.lower() == rule.state.lower():
                                result.append(resource)
        
        return result
