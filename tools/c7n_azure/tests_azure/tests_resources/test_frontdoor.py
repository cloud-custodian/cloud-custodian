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

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-front-door',
            'resource': 'azure.front-door',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccfrontdoor*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_waf_not_enabled(self):
        p = self.load_policy({
            'name': 'waf',
            'resource': 'azure.front-door',
             'filters': [
                {
                    'type': 'waf',
                    'state': 'Disabled'
                },
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
