# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
