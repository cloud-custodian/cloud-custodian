# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from abc import abstractmethod

from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.utils import resolve_service_tag_alias
from netaddr import IPAddress

from c7n.filters.core import type_schema


class SetFirewallAction(AzureBaseAction):

    schema = type_schema(
        'set-firewall-rules',
        required=[],
        **{
            'append': {'type': 'boolean', 'default': True},
            'bypass-rules': {'type': 'array'},
            'ip-rules': {'type': 'array', 'items': {'type': 'string'}},
            'virtual-network-rules': {'type': 'array', 'items': {'type': 'string'}}
        }
    )

    @abstractmethod
    def __init__(self, data, manager=None):
        super(SetFirewallAction, self).__init__(data, manager)

    def _prepare_processing(self):
        self.client = self.manager.get_client()
        self.append = self.data.get('append', True)

    @abstractmethod
    def _process_resource(self, resource):
        pass

    def _build_bypass_rules(self, existing_bypass, new_rules):
        if self.append:
            without_duplicates = [r for r in existing_bypass if r not in new_rules]
            new_rules.extend(without_duplicates)
        return ','.join(new_rules or ['None'])

    def _build_vnet_rules(self, existing_vnet, new_rules):
        if self.append:
            without_duplicates = [r for r in existing_vnet if r not in new_rules]
            new_rules.extend(without_duplicates)
        return new_rules

    def _build_ip_rules(self, existing_ip, new_rules):
        rules = []
        for rule in new_rules:
            # attempt to resolve this rule as a service tag alias
            # if it isn't a valid alias then we'll get `None` back.
            resolved_set = resolve_service_tag_alias(rule)
            if resolved_set:
                # this is a service tag alias, so we need to insert the whole
                # aliased array into the ruleset
                ranges = list(resolved_set.iter_cidrs())
                for r in range(len(ranges)):
                    if len(ranges[r]) == 1:
                        ranges[r] = IPAddress(ranges[r].first)
                rules.extend(map(str, ranges))
            else:
                # just a normal rule, append
                rules.append(rule)

        if self.append:
            for ip in existing_ip:
                if str(ip) not in rules:
                    rules.append(str(ip))
        return rules
