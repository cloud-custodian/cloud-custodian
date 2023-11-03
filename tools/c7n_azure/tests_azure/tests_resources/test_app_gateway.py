# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, cassette_name


class ApplicationGatewayTest(BaseTest):
    def test_app_gateway_validate(self):
        p = self.load_policy({
            'name': 'test-app-gateway',
            'resource': 'azure.application-gateway'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-app-gateway',
            'resource': 'azure.application-gateway',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccgateway*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    # @arm_template('vm.json')
    @cassette_name('test_find_waf')
    def test_find_app_gateway_wo_waf(self):
        p = self.load_policy({
            'name': 'test-app-gateway',
            'resource': 'azure.application-gateway',
            'filters': [
                {'type': 'waf',
                 'state': 'disabled'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @cassette_name('test_find_waf')
    def test_find_app_gateway_with_waf(self):
        p = self.load_policy({
            'name': 'test-app-gateway',
            'resource': 'azure.application-gateway',
            'filters': [
                {'type': 'waf',
                 'state': 'enabled'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 3)

    @cassette_name('test_find_waf')
    def test_find_waf_disabled_rule(self):
        p = self.load_policy({
            'name': 'test-app-gateway',
            'resource': 'azure.application-gateway',
            'filters': [
                {'type': 'waf',
                 'override_rule': 944240}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 4)

    @cassette_name('test_find_waf')
    def test_find_waf_enabled_rule(self):
        p = self.load_policy({
            'name': 'test-app-gateway',
            'resource': 'azure.application-gateway',
            'filters': [
                {'type': 'waf',
                 'override_rule': 944200,
                 'state': 'enabled'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 3)
