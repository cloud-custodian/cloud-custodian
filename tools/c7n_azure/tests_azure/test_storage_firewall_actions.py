# Copyright 2015-2018 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import re

from azure.mgmt.storage.models import StorageAccountUpdateParameters, Action, DefaultAction
from .azure_common import BaseTest, arm_template
from c7n_azure.session import Session

from c7n.utils import local_session

rg_name = 'test_storage'


class StorageTestFirewallActions(BaseTest):
    def setUp(self):
        super(StorageTestFirewallActions, self).setUp()
        self.client = local_session(Session).client('azure.mgmt.storage.StorageManagementClient')

    def tearDown(self):
        resources = self._get_resources()
        self.assertEqual(len(resources), 1)
        resource = resources[0]
        resource.network_rule_set.ip_rules = []
        resource.network_rule_set.virtual_network_rules = []
        resource.network_rule_set.bypass = 'AzureServices'
        resource.network_rule_set.default_action = DefaultAction.allow
        self.client.storage_accounts.update(
            rg_name,
            resource.name,
            StorageAccountUpdateParameters(network_rule_set=resource.network_rule_set))

    @arm_template('storage.json')
    def test_network_ip_rules_action(self):
        p_add = self.load_policy({
            'name': 'test-azure-storage-add-ips',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'default-action': 'Deny',
                 'bypass-rules': ['Logging', 'Metrics'],
                 'ip-rules': ['11.12.13.14', '21.22.23.24']
                 }
            ]
        })

        p_add.run()

        resources = self._get_resources()
        self.assertEqual(len(resources), 1)
        ip_rules = resources[0].network_rule_set.ip_rules
        self.assertEqual(len(ip_rules), 2)
        self.assertEqual(ip_rules[0].ip_address_or_range, '11.12.13.14')
        self.assertEqual(ip_rules[1].ip_address_or_range, '21.22.23.24')
        self.assertEqual(ip_rules[0].action, Action.allow)
        self.assertEqual(ip_rules[1].action, Action.allow)

    @arm_template('storage.json')
    def test_virtual_network_rules_action(self):
        subscription_id = local_session(Session).get_subscription_id()

        id1 = '/subscriptions/' + subscription_id + \
              '/resourceGroups/test_storage/providers/Microsoft.Network/virtualNetworks/' \
              'cctstoragevnet1/subnets/testsubnet1'
        id2 = '/subscriptions/' + subscription_id + \
              '/resourceGroups/test_storage/providers/Microsoft.Network/virtualNetworks/'\
              'cctstoragevnet2/subnets/testsubnet2'

        p_add = self.load_policy({
            'name': 'test-azure-storage-add-ips',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'default-action': 'Deny',
                 'bypass-rules': ['Logging', 'Metrics'],
                 'virtual-network-rules': [id1, id2]
                 }
            ]
        })

        p_add.run()

        resources = self._get_resources()
        self.assertEqual(len(resources), 1)
        rules = resources[0].network_rule_set.virtual_network_rules
        self.assertEqual(len(rules), 2)
        self._assert_equal_resource_ids(rules[0].virtual_network_resource_id, id1)
        self._assert_equal_resource_ids(rules[1].virtual_network_resource_id, id2)
        self.assertEqual(rules[0].action, Action.allow)
        self.assertEqual(rules[1].action, Action.allow)

    @arm_template('storage.json')
    def test_empty_bypass_network_rules_action(self):
        p_add = self.load_policy({
            'name': 'test-azure-storage-add-ips',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'default-action': 'Deny',
                 'bypass-rules': []}
            ]
        })

        p_add.run()

        resources = self._get_resources()
        bypass = resources[0].network_rule_set.bypass
        self.assertEqual('AzureServices', bypass)

    @arm_template('storage.json')
    def test_missing_bypass_network_rules_action(self):
        p_add = self.load_policy({
            'name': 'test-azure-storage-add-ips',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'default-action': 'Deny'}
            ]
        })

        p_add.run()

        resources = self._get_resources()
        bypass = resources[0].network_rule_set.bypass
        self.assertEqual('AzureServices', bypass)

        action = resources[0].network_rule_set.default_action
        self.assertEqual(DefaultAction.deny, action)

    @arm_template('storage.json')
    def test_bypass_network_rules_action(self):
        p_add = self.load_policy({
            'name': 'test-azure-storage-add-ips',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'default-action': 'Deny',
                 'bypass-rules': ['Metrics', 'AzureServices']}
            ]
        })

        p_add.run()

        resources = self._get_resources()
        bypass = resources[0].network_rule_set.bypass
        self.assertEqual(bypass, 'Metrics, AzureServices')

    def _get_resources(self):
        resources = [
            r for r in self.client.storage_accounts.list_by_resource_group(rg_name)
            if r.name.startswith('cctstorage')]
        return resources

    def _assert_equal_resource_ids(self, id1, id2):
        sub_id_regexp = r"/subscriptions/[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}"
        self.assertEqual(re.sub(sub_id_regexp, '', id1), re.sub(sub_id_regexp, '', id2))
