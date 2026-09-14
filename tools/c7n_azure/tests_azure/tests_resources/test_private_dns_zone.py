# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template


class PrivateDnsZoneTest(BaseTest):

    def test_private_dns_zone_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'azure-private-dns-zone-policy',
                'resource': 'azure.private-dns-zone'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('private-dns.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-find-by-name',
            'resource': 'azure.private-dns-zone',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'regex',
                    'value': '^c7n-test\\..*\\.cloudcustodiantest\\.com$'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['name'].startswith('c7n-test.'))
