# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template


class DnsZoneTest(BaseTest):

    def test_dns_zone_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'azure-dns-policy',
                'resource': 'azure.dnszone'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('dns.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-find-by-name',
            'resource': 'azure.dnszone',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'regex',
                    'value': '.*\\.cloudcustodiantest\\.com$'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['name'].endswith('.cloudcustodiantest.com'))
