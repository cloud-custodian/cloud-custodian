# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from azure.mgmt.storage.models import (DefaultAction,
                                       StorageAccountUpdateParameters)
from c7n.utils import local_session
from c7n_azure.session import Session

from .azure_common import BaseTest, arm_template

rg_name = 'test_storage'


class StorageTestFirewallActions(BaseTest):
    def setUp(self):
        super(StorageTestFirewallActions, self).setUp()
        self.client = local_session(Session).client('azure.mgmt.storage.StorageManagementClient')
        self.backup_resources = self._get_resources()
        self.restore = []

    def tearDown(self):
        for restore in self.restore:
            resource = next(r for r in self.backup_resources if r.name.startswith(restore))
            self.client.storage_accounts.update(
                rg_name,
                resource.name,
                StorageAccountUpdateParameters(network_rule_set=resource.network_rule_set))
        super(StorageTestFirewallActions, self).tearDown()

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

        self.restore = ['cctstorage']
        p_add.run()

        resource = self._get_resource('cctstorage')
        ip_rules = resource.network_rule_set.ip_rules
        self.assertEqual(len(ip_rules), 2)
        self.assertEqual(ip_rules[0].ip_address_or_range, '11.12.13.14')
        self.assertEqual(ip_rules[1].ip_address_or_range, '21.22.23.24')
        self.assertEqual(ip_rules[0].action, 'Allow')
        self.assertEqual(ip_rules[1].action, 'Allow')

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

        self.restore = ['cctstorage']
        p_add.run()

        resource = self._get_resource('cctstorage')
        rules = resource.network_rule_set.virtual_network_rules
        self.assertEqual(len(rules), 2)
        self._assert_equal_resource_ids(rules[0].virtual_network_resource_id, id1)
        self._assert_equal_resource_ids(rules[1].virtual_network_resource_id, id2)
        self.assertEqual(rules[0].action, 'Allow')
        self.assertEqual(rules[1].action, 'Allow')

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

        self.restore = ['cctstorage']
        p_add.run()

        resource = self._get_resource('cctstorage')
        bypass = resource.network_rule_set.bypass
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

        self.restore = ['cctstorage']
        p_add.run()

        resource = self._get_resource('cctstorage')
        bypass = resource.network_rule_set.bypass
        self.assertEqual('AzureServices', bypass)

        action = resource.network_rule_set.default_action
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

        self.restore = ['cctstorage']
        p_add.run()

        resource = self._get_resource('cctstorage')
        bypass = resource.network_rule_set.bypass
        self.assertEqual(bypass, 'Metrics, AzureServices')

    @arm_template('storage.json')
    def test_network_ip_rules_append_action(self):
        p_add = self.load_policy({
            'name': 'test-azure-storage-add-ips',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'default-action': 'Deny',
                 'bypass-rules': ['Logging', 'Metrics'],
                 'ip-rules': ['11.12.13.14', '21.22.23.24']
                 }
            ]
        })

        self.restore = ['ccipstorage']
        p_add.run()

        resource = self._get_resource('ccipstorage')
        ip_rules = resource.network_rule_set.ip_rules
        self.assertEqual(len(ip_rules), 4)
        self.assertListEqual([r.ip_address_or_range for r in ip_rules],
                             ['11.12.13.14', '21.22.23.24', '3.1.1.1', '1.2.2.128/25'])

    def _get_resources(self):
        return [r for r in self.client.storage_accounts.list_by_resource_group(rg_name)]

    def _get_resource(self, prefix):
        resources = [
            r for r in self._get_resources()
            if r.name.startswith(prefix)]
        self.assertEqual(1, len(resources))
        return resources[0]

    def _assert_equal_resource_ids(self, id1, id2):
        sub_id_regexp = r"/subscriptions/[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}"
        self.assertEqual(re.sub(sub_id_regexp, '', id1), re.sub(sub_id_regexp, '', id2))
