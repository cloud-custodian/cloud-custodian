# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class AfdCustomDomainTest(BaseTest):

    def test_afd_custom_domain_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-afd-custom-domain',
                'resource': 'azure.afd-custom-domain'
            }, validate=True)
            self.assertTrue(p)

    def test_find_with_mintlsversion_12(self):
        p = self.load_policy({
            'name': 'test-azure-afd-custom-domain',
            'resource': 'azure.afd-custom-domain',
            'filters': [
                {'type': 'value',
                 'key': 'properties.tlsSettings.minimumTlsVersion',
                 'value': 'TLS12'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test-custom-domain')
