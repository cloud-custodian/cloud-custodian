# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class WebAppTest(BaseTest):
    def setUp(self):
        super(WebAppTest, self).setUp()

    def test_validate_webapp_schema(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-azure-webapp',
                'resource': 'azure.webapp'
            }, validate=True)

            self.assertTrue(p)

    @arm_template('webapp.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-webapp',
            'resource': 'azure.webapp',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestwebapp*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('webapp.json')
    def test_find_by_min_tls(self):
        # webapp.json deploys a webapp with minTlsVerion='1.0'
        p = self.load_policy({
            'name': 'test-azure-webapp',
            'resource': 'azure.webapp',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestwebapp*'},
                {
                    'type': 'configuration',
                    'key': 'minTlsVersion',
                    'value': '1.2',
                    'op': 'ne'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('webapp.json')
    def test_find_by_auth_disabled(self):
        # webapp.json deploys a webapp without authentication
        p = self.load_policy({
            'name': 'test-azure-webapp',
            'resource': 'azure.webapp',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestwebapp*'},
                {
                    'type': 'authentication',
                    'key': 'enabled',
                    'value': False,
                    'op': 'eq'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
