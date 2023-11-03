# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('waf')
class WAF(ArmResourceManager):
    """Azure Web Application Firewall Resource

    :example:

    This policy will find all Web Application Firewall

    .. code-block:: yaml

        policies:
          - name: all-web-application-firewall
            resource: azure.waf
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('web_application_firewall_policies', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies'
