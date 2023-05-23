# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class FrontDoorTest(BaseTest):
    def test_azure_front_door_schema_validate(self):
        p = self.load_policy({
            'name': 'test-front-door',
            'resource': 'azure.front-door'
        }, validate=True)
        self.assertTrue(p)
  
    def test_frontdoor_waf_managed_rule_enabled(self):
        p = self.load_policy({
            'name': 'frontdoor-waf-managed-rule-is-enabled',
            'resource': 'azure.frontdoor-waf',
             'filters': [
                {
                    'type': 'value',
                    'key': 'type',
                    'op': 'eq',
                    'value': 'Microsoft.Network/frontdoorWebApplicationFirewallPolicies'
                },
                {
                    'type': 'value',
                    'key': 'sku.name',
                    'op': 'in',
                    'value': ['Premium_AzureFrontDoor','Classic_AzureFrontDoor'],   
                },
                {
                    'type': 'frontdoor-waf-managed-rule-is-enabled',
                    'group': 'JAVA',
                    'id': 944240
                },
              
               
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)