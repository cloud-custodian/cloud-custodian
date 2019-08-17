# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from abc import abstractmethod

from azure.mgmt.storage.models import IPRule, \
    NetworkRuleSet, StorageAccountUpdateParameters, VirtualNetworkRule
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.utils import resolve_service_tag_alias
from netaddr import IPAddress

from c7n.filters.core import type_schema


class SetNetworkRulesAction(AzureBaseAction):
    """ Set Network Rules Action

    Updates Azure Storage Firewalls and Virtual Networks settings.

    By default the firewall rules are replaced with the new values.  The ``append``
    flag can be used to force merging the new rules with the existing ones on
    the resource.

    You may also reference azure public cloud Service Tags by name in place of
    an IP address.  Use ``ServiceTags.`` followed by the ``name`` of any group
    from https://www.microsoft.com/en-us/download/details.aspx?id=56519.

    Note that there are firewall rule number limits and that you will likely need to
    use a regional block to fit within the limit.  The limit for storage accounts is
    200 rules.

    .. code-block:: yaml

        - type: set-firewall-rules
              bypass-rules:
                  - Logging
                  - Metrics
              ip-rules:
                  - 11.12.13.0/16
                  - ServiceTags.AppService.CentralUS


    :example:

    Find storage accounts without any firewall rules.

    Configure default-action to ``Deny`` and then allow:
    - Azure Logging and Metrics services
    - Two specific IPs
    - Two subnets

    .. code-block:: yaml

        policies:
            - name: add-storage-firewall
              resource: azure.storage

            filters:
                - type: value
                  key: properties.networkAcls.ipRules
                  value_type: size
                  op: eq
                  value: 0

            actions:
                - type: set-firewall-rules
                  bypass-rules:
                      - Logging
                      - Metrics
                  ip-rules:
                      - 11.12.13.0/16
                      - 21.22.23.24
                  virtual-network-rules:
                      - <subnet_resource_id>
                      - <subnet_resource_id>

    """

    schema = type_schema(
        'set-firewall-rules',
        required=[],
        **{
            'default-action': {'enum': ['Allow', 'Deny'], "default": 'Deny'},
            'append': {'type': 'boolean', "default": False},
            'bypass-rules': {'type': 'array', 'items': {
                'enum': ['AzureServices', 'Logging', 'Metrics']}},
            'ip-rules': {'type': 'array', 'items': {'type': 'string'}},
            'virtual-network-rules': {'type': 'array', 'items': {'type': 'string'}}
        }
    )

    @abstractmethod
    def __init__(self, data, manager=None):
        super(SetNetworkRulesAction, self).__init__(data, manager)

    def _prepare_processing(self):
        self.client = self.manager.get_client()
        self.append = self.data.get('append', False)

    @abstractmethod
    def _process_resource(self, resource):
        pass

    def _build_bypass_rules(self, resource, new_rules):
        if self.append:
            existing_bypass = resource['properties']['networkAcls'].get('bypass', '').split(',')
            without_duplicates = [r for r in existing_bypass if r not in new_rules]
            new_rules.extend(without_duplicates)
        return ','.join(new_rules or ['None'])

    def _build_vnet_rules(self, resource, new_rules):
        if self.append:
            existing_rules = [r['id'] for r in
                              resource['properties']['networkAcls'].get('virtualNetworkRules', [])]
            without_duplicates = [r for r in existing_rules if r not in new_rules]
            new_rules.extend(without_duplicates)
        return new_rules

    def _build_ip_rules(self, resource, new_rules):
        rules = []
        for rule in new_rules:
            resolved_set = resolve_service_tag_alias(rule)
            if resolved_set:
                ranges = list(resolved_set.iter_cidrs())
                for r in range(len(ranges)):
                    if len(ranges[r]) == 1:
                        ranges[r] = IPAddress(ranges[r].first)
                rules.extend(map(str, ranges))
            else:
                rules.append(rule)

        if self.append:
            existing_rules = resource['properties']['networkAcls'].get('ipRules', [])
            without_duplicates = [r['value'] for r in existing_rules if r['value'] not in rules]
            rules.extend(without_duplicates)
        return rules
