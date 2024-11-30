# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class AfdEndpointTest(BaseTest):

    def test_afd_endpoint_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-afd-endpoint',
                'resource': 'azure.afd-endpoint'
            }, validate=True)
            self.assertTrue(p)

    def test_find_enabled_endpoints(self):
        p = self.load_policy({
            'name': 'test-azure-afd-endpoint',
            'resource': 'azure.afd-endpoint',
            'filters': [
                {'type': 'value',
                 'key': 'properties.enabledState',
                 'value': 'Enabled'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test-endpoint')
