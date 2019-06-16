# Copyright 2018 Capital One Services, LLC
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

from c7n_azure.filters import FirewallRulesFilter
from azure.mgmt.storage.models import IPRule, \
    NetworkRuleSet, StorageAccountUpdateParameters, VirtualNetworkRule
from c7n.filters.core import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from netaddr import IPNetwork


@resources.register('storage')
class Storage(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.storage'
        client = 'StorageManagementClient'
        enum_spec = ('storage_accounts', 'list', None)
        diagnostic_settings_enabled = False
        resource_type = 'Microsoft.Storage/storageAccounts'


@Storage.action_registry.register('set-network-rules')
class StorageSetNetworkRulesAction(AzureBaseAction):

    schema = type_schema(
        'set-network-rules',
        required=['default-action'],
        **{
            'default-action': {'enum': ['Allow', 'Deny']},
            'bypass': {'type': 'array', 'items': {'enum': ['AzureServices', 'Logging', 'Metrics']}},
            'ip-rules': {
                'type': 'array',
                'items': {'ip-address-or-range': {'type': 'string'}}
            },
            'virtual-network-rules': {
                'type': 'array',
                'items': {'virtual-network-resource-id': {'type': 'string'}}
            }
        }
    )

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        rule_set = NetworkRuleSet(default_action=self.data['default-action'])

        if 'ip-rules' in self.data:
            rule_set.ip_rules = [
                IPRule(
                    ip_address_or_range=r['ip-address-or-range'],
                    action='Allow')  # 'Allow' is the only allowed action
                for r in self.data['ip-rules']]

        if 'virtual-network-rules' in self.data:
            rule_set.virtual_network_rules = [
                VirtualNetworkRule(
                    virtual_network_resource_id=r['virtual-network-resource-id'],
                    action='Allow')  # 'Allow' is the only allowed action
                for r in self.data['virtual-network-rules']]

        if len(self.data.get('bypass', [])) > 0:
            rule_set.bypass = ','.join(self.data['bypass'])
        else:
            rule_set.bypass = 'None'

        self.client.storage_accounts.update(
            resource['resourceGroup'],
            resource['name'],
            StorageAccountUpdateParameters(network_rule_set=rule_set))


@Storage.filter_registry.register('firewall-rules')
class StorageFirewallRulesFilter(FirewallRulesFilter):

    def __init__(self, data, manager=None):
        super(StorageFirewallRulesFilter, self).__init__(data, manager)
        self._log = logging.getLogger('custodian.azure.storage')

    @property
    def log(self):
        return self._log

    def _query_rules(self, resource):

        ip_rules = resource['properties']['networkAcls']['ipRules']

        resource_rules = set([IPNetwork(r['value']) for r in ip_rules])

        return resource_rules
