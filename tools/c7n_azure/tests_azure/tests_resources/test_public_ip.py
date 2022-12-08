# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class PublicIpAddressTest(BaseTest):
    def setUp(self):
        super(PublicIpAddressTest, self).setUp()

    def test_public_ip_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-public-ip',
                'resource': 'azure.publicip'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('vm.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'mypublicip'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
