# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.filters import Filter
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


@CdnProfile.filter_registry.register('waf')
class WebAppFirewallFilter(Filter):
    """Check waf enabled/disabled on cdn profiles

    :example:

    .. code-block:: yaml

        policies:
          - name: test-waf-not-enabled
            resource: azure.cdnprofile
            filters:
                - type: waf
                  state: Disabled
    """
    schema = type_schema(
        'waf',
        required=['state'],
        state={'type': 'string', 'enum': ['Enabled', 'Disabled']})

    def process(self, resources, event=None):
        client = self.manager.get_client()
        matched = []
        for profiles in resources:
            policies = list(client.security_policies.list_by_profile(
                profiles["resourceGroup"], profiles["name"]))
            if (self.data.get('state') == 'Disabled' and not policies) \
               or (self.data.get('state') == 'Enabled' and policies):
                matched.append(profiles)
        return matched
