# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n_azure.utils import ResourceIdParser
from c7n.filters import Filter, ListItemFilter
from c7n.utils import type_schema


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
    schema = type_schema('waf', required=['state'],
            state={'type': 'string', 'enum': ['Enabled', 'Disabled']})

    def check_state(self, link):
        if self.data.get('state') == 'Disabled' and link is None:
            return True
        if self.data.get('state') == 'Enabled' and link is not None:
            return True

    def process(self, resources, event=None):
        matched = []
        for front_door in resources:
            for front_endpoint in front_door['properties']['frontendEndpoints']:
                data = front_endpoint['properties'].get('webApplicationFirewallPolicyLink') or {}
                link = data.get('id')
                if self.check_state(link):
                    matched.append(front_door)
                    break
        return matched


@FrontDoor.filter_registry.register('firewall-policy')
class WAFPolicies(ListItemFilter):
    """Filters front door resources based on their waf policies

    :example:

    .. code-block:: yaml

        policies:
          - name: front-dorr-firewall-policy-example
            resource: azure.front-door
            filters:
              - type: firewall-policy
                attrs:
                  - type: value
                    key: properties.managedRules.managedRuleSets[].ruleSetType
                    value: DefaultRuleSet
                    op: contains

    """
    schema = type_schema(
        'firewall-policy',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'}
    )
    annotate_items = True
    item_annotation_key = 'c7n:WAFPolicies'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}  # policy id to policy item

    def get_item_values(self, resource):
        ids = set()
        for fe in resource['properties'].get('frontendEndpoints') or []:
            data = fe['properties'].get('webApplicationFirewallPolicyLink')
            if not isinstance(data, dict):
                continue
            identifier = data.get('id')
            if not identifier:
                continue
            ids.add(identifier)
        if not ids:
            return []
        client = self.manager.get_client()
        items = []
        for i in ids:
            if i not in self._cache:
                group = ResourceIdParser.get_resource_group(i)
                name = ResourceIdParser.get_resource_name(i)
                self._cache[i] = client.policies.get(group, name)
            item = self._cache[i]
            items.append(item.serialize(True))
        return items
