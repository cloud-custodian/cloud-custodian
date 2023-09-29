# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class AppConfiguration(BaseTest):
    def setUp(self):
        super(AppConfiguration, self).setUp()

    def test_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-app-configuration',
                'resource': 'azure.app-configuration'
            }, validate=True)
            self.assertTrue(p)

    def test_valid_private_endpoint_connections(self):
        p = self.load_policy({
            'name': 'azure-app-configuration',
            'resource': 'azure.app-configuration',
            'filters': [{
                'type': 'value',
                'key': 'properties.privateEndpointConnections[].properties.'
                       'privateLinkServiceConnectionState.status',
                'value': 'Approved',
                'op': 'contains',
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('vv1appconf', resources[0]['name'])
