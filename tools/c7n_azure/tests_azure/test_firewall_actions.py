# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock

from .azure_common import BaseTest
from c7n_azure.resources.storage import StorageSetFirewallAction
import pytest


class FirewallActionsTest(BaseTest):

    def test_build_bypass_rules(self):
        data = {
            'type': 'set-firewall-rules',
            'bypass-rules': ['Logging', 'Metrics'],
        }

        action = StorageSetFirewallAction(data)
        action.append = False
        rules = action._build_bypass_rules(['Hello', 'World'], data['bypass-rules'])
        self.assertEqual('Logging,Metrics', rules)

        action.append = True
        rules = action._build_bypass_rules(['Hello', 'World'], data['bypass-rules'])
        self.assertEqual('Logging,Metrics,Hello,World', rules)

    def test_build_bypass_rules_drops_the_none_sentinel(self):
        action = self._bypass_action(['AzureServices'])

        # 'None' means "bypass nothing"; merging it as a member is not a valid value.
        assert action._build_bypass_rules(
            'None'.split(','), action.data['bypass-rules']) == 'AzureServices'

    def test_build_bypass_rules_ignores_an_absent_bypass_value(self):
        action = self._bypass_action(['AzureServices'])

        # storage.py falls back to '' when the account has no bypass key.
        assert action._build_bypass_rules(
            ''.split(','), action.data['bypass-rules']) == 'AzureServices'

    def test_build_bypass_rules_matches_existing_values_with_whitespace(self):
        action = self._bypass_action(['Metrics'])

        # Azure returns the string comma-space separated.
        assert action._build_bypass_rules(
            'Logging, Metrics'.split(','), action.data['bypass-rules']) == 'Metrics,Logging'

    def test_build_bypass_rules_does_not_carry_over_between_resources(self):
        action = self._bypass_action(['AzureServices'])

        first = action._build_bypass_rules('Logging'.split(','), action.data['bypass-rules'])
        second = action._build_bypass_rules('Metrics'.split(','), action.data['bypass-rules'])

        assert first == 'AzureServices,Logging'
        assert second == 'AzureServices,Metrics'
        assert action.data['bypass-rules'] == ['AzureServices']

    def test_build_bypass_rules_empty_result_is_the_none_sentinel(self):
        action = self._bypass_action([], append=False)

        assert action._build_bypass_rules('Logging'.split(','), action.data['bypass-rules']) \
            == 'None'

    def test_build_vnet_rules_does_not_carry_over_between_resources(self):
        action = StorageSetFirewallAction(
            {'type': 'set-firewall-rules', 'virtual-network-rules': []})
        action.append = True

        first = action._build_vnet_rules(['id1'], action.data['virtual-network-rules'])
        second = action._build_vnet_rules(['id2'], action.data['virtual-network-rules'])

        assert first == ['id1']
        assert second == ['id2']
        assert action.data['virtual-network-rules'] == []

    def test_build_vnet_rules(self):
        data = {
            'virtual-network-rules': ['id1', 'id2']
        }

        action = StorageSetFirewallAction(data)
        action.append = False
        rules = action._build_vnet_rules(['Hello', 'World'], data['virtual-network-rules'])
        self.assertEqual(sorted(['id1', 'id2']), sorted(rules))

        action.append = True
        rules = action._build_vnet_rules(['Hello', 'World'], data['virtual-network-rules'])
        self.assertEqual(sorted(['id1', 'id2', 'Hello', 'World']), sorted(rules))

    def test_build_ip_rules(self):
        data = {
            'ip-rules': ['1.1.1.1', '6.0.0.0/16']
        }

        action = StorageSetFirewallAction(data)
        action.append = False
        rules = action._build_ip_rules(['1.1.1.1', '8.0.0.0/12'], data['ip-rules'])
        self.assertEqual(sorted(['1.1.1.1', '6.0.0.0/16']), sorted(rules))

        action.append = True
        rules = action._build_ip_rules(['1.1.1.1', '8.0.0.0/12'], data['ip-rules'])
        self.assertEqual(sorted(['1.1.1.1', '6.0.0.0/16', '8.0.0.0/12']), sorted(rules))

    # Service Tag IP lists are dynamic and will always be changing in live tests
    @pytest.mark.skiplive
    def test_build_ip_rules_alias(self):
        data = {
            'ip-rules': ['ServiceTags.ApiManagement.WestUS', '6.0.0.0/16']
        }

        action = StorageSetFirewallAction(data)
        action.append = False
        rules = action._build_ip_rules(['1.1.1.1', '8.0.0.0/12'], data['ip-rules'])
        self.assertIn('6.0.0.0/16', rules)
        self.assertEqual(4, len(rules))

        # With append we expect all our specified values + others from the service tag.
        action.append = True
        rules = action._build_ip_rules(['1.1.1.1', '8.0.0.0/12'], data['ip-rules'])
        self.assertTrue({'6.0.0.0/16', '1.1.1.1', '8.0.0.0/12'} <= set(rules))
        self.assertEqual(6, len(rules))

    def test_process_resource_keeps_each_account_to_its_own_rules(self):
        action = StorageSetFirewallAction({
            'type': 'set-firewall-rules',
            'default-action': 'Deny',
            'bypass-rules': ['AzureServices'],
            'virtual-network-rules': [],
        })
        action.append = True
        action.client = Mock()

        for name, acls in [
            ('hr', {'bypass': 'None', 'virtualNetworkRules': [{'id': '/subnets/hr'}]}),
            ('public', {'bypass': 'None', 'virtualNetworkRules': []}),
        ]:
            action._process_resource(
                {'name': name, 'resourceGroup': 'rg', 'properties': {'networkAcls': acls}})

        sent = [c[0][2].network_rule_set
                for c in action.client.storage_accounts.update.call_args_list]

        assert [r.bypass for r in sent] == ['AzureServices', 'AzureServices']
        # The account with no VNet access must not inherit the one processed before it.
        assert [[v.virtual_network_resource_id for v in r.virtual_network_rules]
                for r in sent] == [['/subnets/hr'], []]

    def _bypass_action(self, bypass_rules, append=True):
        action = StorageSetFirewallAction(
            {'type': 'set-firewall-rules', 'bypass-rules': bypass_rules})
        action.append = append
        return action
