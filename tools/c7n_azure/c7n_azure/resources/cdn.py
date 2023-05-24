# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.filters import Filter

from c7n.utils import type_schema

@resources.register('cdnprofile')
class CdnProfile(ArmResourceManager):
    """CDN Resource

    :example:

    Returns all CDNs with Standard_Verizon sku

    .. code-block:: yaml

        policies:
          - name: standard-verizon
            resource: azure.cdnprofile
            filters:
              - type: value
                key: sku
                op: in
                value_type: normalize
                value: Standard_Verizon

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
            'sku.name'
        )
        resource_type = 'Microsoft.Cdn/profiles'

@CdnProfile.filter_registry.register('cdn-waf-is-enabled')
class WebAppFirewallMissingFilter(Filter):
    """CDN check waf enabled on cdn profiles

    :example:

    .. code-block:: yaml

        policies:
            name: test-cdn-waf-is-enabled
            resource: azure.cdnprofile
            filters: [
                - type: cdn-waf-is-enabled
                - type: value
                  key: sku.name
                  op: in
                  value: ['Standard_AzureFrontDoor','Premium_AzureFrontDoor']              
            ]

    """
    schema = type_schema('frontdoor-waf-is-enabled')
    
    def process(self, resources, event=None):
        client = self.manager.get_client()
        results = []
        for r in resources:
            policies = list(client.security_policies.list_by_profile(r["resourceGroup"],r["name"]))
            if not policies:
                results.append(r)
        return results