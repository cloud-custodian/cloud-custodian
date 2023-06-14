# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class VNetTest(BaseTest):
    def setUp(self):
        super(VNetTest, self).setUp()

    def test_validate_vnet_schemas(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-azure-vnet',
                'resource': 'azure.vnet'
            }, validate=True)

            self.assertTrue(p)
    
    def test_vpn_ipsec_filter(self):
        p = self.load_policy({
            'name': 'gw-without-ipsec-policies',
            'resource': 'azure.vnet',
            'filters': [
                {'type': 'gw-without-ipsec-policies'}          
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
