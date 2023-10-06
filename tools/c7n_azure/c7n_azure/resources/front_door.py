# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.filters import Filter, ValueFilter
from c7n.filters.core import op
from c7n.utils import type_schema, local_session
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


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


@FrontDoor.filter_registry.register('web-application-firewall-policies')
class WebApplicationFirewallPolicies(ValueFilter):

    schema = type_schema('web-application-firewall-policies', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        filtered_resources = []
        s = local_session(self.manager.session_factory)
        client = s.client('azure.mgmt.frontdoor.FrontDoorManagementClient')
        for resource in resources:
            for policy in client.policies.list(resource_group_name=resource['resourceGroup']):
                try:
                    pol = getattr(policy, self.data.get('key'))
                except Exception as e:
                    if 'list index out of range' in str(e):
                        continue
                    raise
                if pol and op(self.data, pol, self.data.get('value')):
                    filtered_resources.append(resource)
                    break

        return filtered_resources
