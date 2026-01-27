# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class KeyVaultSecretsTest(BaseTest):

    def tearDown(self, *args, **kwargs):
        super(KeyVaultSecretsTest, self).tearDown(*args, **kwargs)

    def test_key_vault_secrets_schema_validate(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-secret',
        }, validate=True)
        self.assertTrue(p)

    @arm_template('keyvault.json')
    def test_key_vault_secrets_keyvault(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-secret',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cfb*'
                    }
                },
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault.json')
    def test_key_vault_secrets_expiry(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-secret',
            'filters': [
                {
                    'type': 'value',
                    'key': 'attributes.expires',
                    'op': 'equal',
                    'value': 'not-null'
                },
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)
