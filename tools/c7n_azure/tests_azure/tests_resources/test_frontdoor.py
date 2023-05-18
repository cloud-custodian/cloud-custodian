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

    def test_frontdoor_cdn(self):
        p = self.load_policy({
            'name': 'test-frontdoor-cdn',
            'resource': 'azure.frontdoor-cdn'
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)
    
    def test_frontdoor_waf_managed_rule_enabled(self):
        p = self.load_policy({
            'name': 'frontdoor-waf-managed-rule-is-enabled',
            'resource': 'azure.frontdoor-waf',
            'filters': [
                {'type': 'frontdoor-waf-managed-rule-is-enabled',
                 'group': 'JAVA',
                 'id': 944240}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_frontdoor_waf_enabled(self):
        p = self.load_policy({
            'name': 'test-frontdoor-waf-is-enabled',
            'resource': 'azure.frontdoor-cdn',
            'filters': [
                {'type': 'frontdoor-waf-is-enabled'}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)
