# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class AppInsightsTest(BaseTest):
    def setUp(self):
        super(AppInsightsTest, self).setUp()

    def test_app_insights_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-app-insights',
                'resource': 'azure.app-insights'
            }, validate=True)
            self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-app-insights',
            'resource': 'azure.app-insights',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'present'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
