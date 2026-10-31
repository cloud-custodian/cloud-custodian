# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
import textwrap
from unittest.mock import MagicMock, patch

import yaml

from azure.keyvault.keys import KeyProperties
from azure.keyvault.keys._generated.models import KeyAttributes

from c7n.exceptions import PolicyValidationError
from c7n_azure.query import _serialize
from c7n_azure.resources.key_vault_keys import KeyVaultKeyUpdateAction

from ..azure_common import BaseTest, arm_template


class KeyVaultKeyTest(BaseTest):

    def tearDown(self, *args, **kwargs):
        super(KeyVaultKeyTest, self).tearDown(*args, **kwargs)

    def test_key_vault_keys_schema_validate(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-keys',
            'filters': [
                {'type': 'keyvault', 'vaults': ['kv1', 'kv2']},
                {'type': 'key-type', 'key-types': ['RSA', 'RSA-HSM', 'EC', 'EC-HSM']}
            ]
        }, validate=True)
        self.assertTrue(p)

        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-key',
            'filters': [
                {'type': 'keyvault', 'vaults': ['kv1', 'kv2']},
                {'type': 'key-type', 'key-types': ['RSA', 'RSA-HSM', 'EC', 'EC-HSM']}
            ]
        }, validate=True)
        self.assertTrue(p)

    @arm_template('keyvault.json')
    def test_key_vault_keys_keyvault(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-key',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cckeyvault1*'
                    }
                },
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    @arm_template('keyvault.json')
    def test_key_vault_keys_type(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-key',
            'filters': [
                {
                    'type': 'key-type',
                    'key-types': ['RSA', 'RSA-HSM']
                },
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['c7n:kty'].lower(), 'rsa')

    def test_key_vault_keys_rotation(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-key',
            'filters': [
                {
                    'type': 'rotation-policy',
                    'state': 'Disabled'
                }
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_key_vault_key_update_action(self):
        p = self.load_policy(
            {
                "name": "test-key-vault-key-update-action",
                "resource": "azure.keyvault-key",
                "filters": [
                    {
                        'type': 'parent',
                        'filter': {
                            'type': 'value',
                            'key': 'name',
                            'op': 'eq',
                            'value': 'c7ntestvault'
                        }
                    },
                    {
                        'attributes.data.enabled': False
                    }
                ],
                "actions": [
                    {
                        "type": "update",
                        "enabled": True
                    }
                ]
            }
        )
        resources = p.run()

        vault_url = resources[0]['vault_id']['resource_id']['vault_url']
        name = resources[0]['vault_id']['resource_id']['name']

        client = p.resource_manager.get_client(
            vault_url=vault_url
        )
        key = client.get_key(
            name=name
        )
        self.assertTrue(key.properties.enabled)

    def test_key_vault_key_update_expires_on_not_before_action(self):
        p = self.load_policy(
            {
                "name": "test-key-vault-key-update-action",
                "resource": "azure.keyvault-key",
                "filters": [
                    {
                        'type': 'parent',
                        'filter': {
                            'type': 'value',
                            'key': 'name',
                            'op': 'eq',
                            'value': 'c7ntestvault'
                        }
                    },
                    {
                        'attributes.expires_on': None
                    },
                    {
                        'attributes.not_before': None
                    }
                ],
                "actions": [
                    {
                        "type": "update",
                        "not_before": "2025-03-01 00:00:00",
                        "expires_on": "2025-04-01 00:00:00"
                    }
                ]
            }
        )
        resources = p.run()

        vault_url = resources[0]['vault_id']['resource_id']['vault_url']
        name = resources[0]['vault_id']['resource_id']['name']

        client = p.resource_manager.get_client(
            vault_url=vault_url
        )

        key = client.get_key(
            name=name
        )
        self.assertEqual(
            key.properties.expires_on,
            # python 3.9 compat, can't use 00:00:00Z
            datetime.datetime.fromisoformat("2025-04-01 00:00:00+00:00")
        )
        self.assertEqual(
            key.properties.not_before,
            datetime.datetime.fromisoformat("2025-03-01 00:00:00+00:00")
        )

    def _update_policy(self, **action):
        return self.load_policy({
            'name': 'test-key-vault-key-update-expires-in',
            'resource': 'azure.keyvault-key',
            'actions': [dict(type='update', **action)]
        }, validate=True)

    def _run_update(self, **action):
        p = self.load_policy({
            'name': 'test-key-vault-key-update-expires-in',
            'resource': 'azure.keyvault-key',
            'actions': [dict(type='update', **action)]
        })
        client = MagicMock()
        resource = {
            'id': 'https://v.vault.azure.net/keys/k/1',
            'vault_id': {'resource_id': {'name': 'k'}}
        }
        with patch.object(p.resource_manager, 'get_client', return_value=client), \
                patch('c7n_azure.resources.key_vault_keys.utils.utcnow',
                      return_value=datetime.datetime(2026, 1, 1, 12, 0, 0)):
            p.resource_manager.actions[0]._process_resource(resource)
        return client.update_key_properties.call_args.kwargs

    def test_update_expires_in_accepts_valid(self):
        self.assertTrue(self._update_policy(expires_in={'days': 90}))

    def test_update_expires_in_rejects_empty(self):
        with self.assertRaisesRegex(PolicyValidationError, 'should be non-empty'):
            self._update_policy(expires_in={})

    def test_update_expires_in_rejects_zero(self):
        with self.assertRaisesRegex(PolicyValidationError, 'must be greater than zero'):
            self._update_policy(expires_in={'days': 0, 'hours': 0})

    def test_update_expires_in_rejects_negative(self):
        with self.assertRaisesRegex(PolicyValidationError, 'less than the minimum'):
            self._update_policy(expires_in={'days': -1})

    def test_update_expires_in_rejects_fractional(self):
        with self.assertRaisesRegex(PolicyValidationError, "is not of type 'integer'"):
            self._update_policy(expires_in={'days': 1.5})

    def test_update_expires_in_rejects_overflow(self):
        for expires_in in ({'days': 3000000}, {'days': 10 ** 10}):
            with self.assertRaisesRegex(PolicyValidationError, 'too large'):
                self._update_policy(expires_in=expires_in)

    def test_update_expires_in_rejects_with_expires_on(self):
        with self.assertRaisesRegex(PolicyValidationError, 'mutually exclusive'):
            self._update_policy(
                expires_in={'days': 1}, expires_on='2030-01-01 00:00:00')

    def test_update_expires_in_value(self):
        kwargs = self._run_update(
            expires_in={'days': 90, 'hours': 2, 'minutes': 30},
            not_before='2030-01-01 00:00:00')
        self.assertEqual(kwargs['expires_on'], datetime.datetime(2026, 4, 1, 14, 30, 0))
        self.assertEqual(kwargs['not_before'], datetime.datetime(2030, 1, 1, 0, 0))

    def test_update_expires_on_unchanged(self):
        kwargs = self._run_update(expires_on='2030-02-02 00:00:00')
        self.assertEqual(kwargs['expires_on'], datetime.datetime(2030, 2, 2))

    @arm_template('keyvault.json')
    def test_key_vault_key_update_expires_in_action(self):
        p = self.load_policy({
            'name': 'test-key-vault-key-update-expires-in',
            'resource': 'azure.keyvault-key',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cckeyvault1*'
                    }
                },
                {'type': 'value', 'key': 'id', 'op': 'glob', 'value': '*/keys/cctestrsa'},
                {'type': 'value', 'key': 'attributes.data.exp', 'value': 'absent'}
            ],
            'actions': [{'type': 'update', 'expires_in': {'days': 90}}]
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = p.resource_manager.get_client(
            vault_url=resources[0]['vault_id']['resource_id']['vault_url'])
        key = client.get_key(name=resources[0]['vault_id']['resource_id']['name'])
        self.assertEqual(
            key.properties.expires_on.replace(tzinfo=None),
            self._get_test_date() + datetime.timedelta(days=90)
        )

    def test_update_docstring_filter_skips_keys_with_expiration(self):
        # The last docstring example selects keys that have no expiration.
        example = KeyVaultKeyUpdateAction.__doc__.split('.. code-block:: yaml')[-1]
        filters = yaml.safe_load(textwrap.dedent(example))['policies'][0]['filters']
        p = self.load_policy({
            'name': 'test-key-vault-key-docstring-filter',
            'resource': 'azure.keyvault-key',
            'filters': filters
        }, validate=True)

        def key(name, **attributes):
            return _serialize(KeyProperties(
                key_id=f'https://v.vault.azure.net/keys/{name}/1',
                attributes=KeyAttributes(enabled=True, **attributes)))

        expiring = key('expiring', expires=datetime.datetime(
            2030, 1, 1, tzinfo=datetime.timezone.utc))
        matched = p.resource_manager.filter_resources([expiring, key('open')])
        self.assertEqual([r['id'].split('/')[-2] for r in matched], ['open'])
