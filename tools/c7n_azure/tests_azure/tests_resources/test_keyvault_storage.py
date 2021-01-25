# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import azure.keyvault.http_bearer_challenge_cache as kv_cache
from ..azure_common import BaseTest, arm_template, cassette_name
from mock import patch


class KeyVaultStorageTest(BaseTest):

    def tearDown(self, *args, **kwargs):
        super(KeyVaultStorageTest, self).tearDown(*args, **kwargs)
        kv_cache._cache = {}

    def test_key_vault_storage_schema_validate(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-storage',
        }, validate=True)
        self.assertTrue(p)

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_key_vault_storage_query(self):
        p = self._get_policy([], [])
        resources = p.run()
        self.assertEqual(len(resources), 2)

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_key_vault_storage_filter_auto_regenerate(self):
        p = self._get_policy([{'type': 'auto-regenerate-key', 'value': False}], [])
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault.json')
    @cassette_name('common')
    def test_key_vault_storage_filter_regeneration_period(self):
        p = self._get_policy([{'type': 'regeneration-period', 'value': 'P90D'}], [])
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault.json')
    @cassette_name('common')
    # Possible fail reasons:
    #  - KeyVault auto-regenerated the active key, so current active key is 2.
    #    Current auto-regenerate period was set to 720 days.
    def test_key_vault_storage_filter_active_key_name(self):
        p = self._get_policy([{'type': 'active-key-name', 'value': 'key1'}], [])
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault.json')
    @cassette_name('common')
    @patch('azure.keyvault.v7_0.KeyVaultClient.regenerate_storage_account_key')
    def test_key_vault_storage_action_regenerate(self, regenerate_mock):
        p = self._get_policy([{'type': 'active-key-name', 'value': 'key1'}],
                             [{'type': 'regenerate-key'}])
        resources = p.run()
        self.assertEqual(len(resources), 1)

        regenerate_mock.assert_called_once()
        name, args, kwargs = regenerate_mock.mock_calls[0]
        self.assertTrue(args[0].startswith('https://cckeyvault1'))
        self.assertEqual(args[1], 'storage1')
        self.assertEqual(args[2], 'key1')

    @arm_template('keyvault.json')
    @cassette_name('common')
    @patch('azure.keyvault.v7_0.KeyVaultClient.update_storage_account')
    def test_key_vault_storage_action_update(self, update_mock):
        p = self._get_policy([{'type': 'active-key-name', 'value': 'key1'}],
                             [{'type': 'update',
                               'active-key-name': 'key2',
                               'auto-regenerate-key': True,
                               'regeneration-period': 'P1D'}])
        resources = p.run()
        self.assertEqual(len(resources), 1)

        update_mock.assert_called_once()
        name, args, kwargs = update_mock.mock_calls[0]
        self.assertTrue(args[0].startswith('https://cckeyvault1'))
        self.assertEqual(args[1], 'storage1')
        self.assertEqual(kwargs['active_key_name'], 'key2')
        self.assertEqual(kwargs['auto_regenerate_key'], True)
        self.assertEqual(kwargs['regeneration_period'], 'P1D')

    @arm_template('keyvault.json')
    @cassette_name('common')
    @patch('azure.keyvault.v7_0.KeyVaultClient.update_storage_account')
    def test_key_vault_storage_action_update_empty(self, update_mock):
        p = self._get_policy([{'type': 'active-key-name', 'value': 'key1'}],
                             [{'type': 'update'}])
        resources = p.run()
        self.assertEqual(len(resources), 1)

        update_mock.assert_called_once()
        name, args, kwargs = update_mock.mock_calls[0]
        self.assertTrue(args[0].startswith('https://cckeyvault1'))
        self.assertEqual(args[1], 'storage1')
        self.assertEqual(kwargs['active_key_name'], None)
        self.assertEqual(kwargs['auto_regenerate_key'], None)
        self.assertEqual(kwargs['regeneration_period'], None)

    def _get_policy(self, filters, actions):
        return self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-storage',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cckeyvault1*'
                    }
                }
            ] + filters,
            'actions': actions
        }, validate=True, cache=True)
