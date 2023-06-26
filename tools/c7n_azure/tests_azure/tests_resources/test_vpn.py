# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class VPNTest(BaseTest):
    def setUp(self):
        super(VPNTest, self).setUp()

    def test_validate_vpn_schemas(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-azure-vnet',
                'resource': 'azure.vnet'
            }, validate=True)

            self.assertTrue(p)

    def test_vpn_ipsec_filter(self):
        p = self.load_policy({
            'name': 'gw-without-ipsec-policies',
            'resource': 'azure.vpn',
            'filters': [
                {'type': 'gw-without-ipsec-policies',
                 'state': 'Disabled'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
