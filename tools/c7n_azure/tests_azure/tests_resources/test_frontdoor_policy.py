# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class FrontDoorPolicyTest(BaseTest):
    def test_azure_front_door_policy_schema_validate(self):
        p = self.load_policy({
            'name': 'test-front-door-policy',
            'resource': 'azure.front-door-policy'
        }, validate=True)
        self.assertTrue(p)

    def test_front_door_policy_schema(self):
        p = self.load_policy({
            'name': 'test-front-door-policy-schema',
            'resource': 'azure.front-door-policy'
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_front_door_policy_schema1(self):
        p = self.load_policy({
        'name': 'test-front-door-policy-schema',
        'resource': 'azure.front-door-policy',
        'filters': [
            {
                'type': 'value',
                'key':
        'properties.managedRules.managedRuleSets[].ruleGroupOverrides[].rules[].ruleId',
                'value_type': 'swap',
                'op': 'in',
                'value': '944240'
            },
            {
                'type': 'value',
                'key':
        'properties.managedRules.managedRuleSets[].ruleGroupOverrides[].rules[].enabledState',
                'value_type': 'swap',
                'op': 'in',
                'value': 'Disabled'
            }
        ]})
        resources = p.run()
        self.assertEqual(len(resources), 1)
