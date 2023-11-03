# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class WAFTest(BaseTest):
    def test_waf_validate(self):
        p = self.load_policy({
            'name': 'test-waf',
            'resource': 'azure.waf'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-waf',
            'resource': 'azure.waf',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cfb*'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
