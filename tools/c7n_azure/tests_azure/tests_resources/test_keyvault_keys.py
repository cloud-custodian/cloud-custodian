# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime

from azure.keyvault.keys import KeyRotationPolicyAction

from c7n.exceptions import PolicyValidationError

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

    def _rotation_policy(self, name, filters=(), actions=()):
        vault_filter = {
            'type': 'parent',
            'filter': {'type': 'value', 'key': 'name', 'value': 'c7ntestvault'}
        }
        return self.load_policy({
            'name': name,
            'resource': 'azure.keyvault-key',
            'filters': [vault_filter] + list(filters),
            'actions': list(actions),
        }, validate=True)

    def _key_names(self, resources):
        return sorted(r['id'].rsplit('/', 1)[-1] for r in resources)

    def test_key_vault_keys_rotation_auto_rotation(self):
        # notify-key has a saved rotation policy that only notifies, so it is never rotated.
        p = self._rotation_policy('test-key-vault-keys-auto-rotation', filters=[
            {'type': 'rotation-policy', 'state': 'Disabled', 'auto-rotation': True}])
        self.assertEqual(self._key_names(p.run()), ['notify-key'])

    def test_key_vault_keys_rotation_notify_only_is_enabled(self):
        p = self._rotation_policy('test-key-vault-keys-rotation-enabled', filters=[
            {'type': 'rotation-policy', 'state': 'Enabled'}])
        self.assertEqual(self._key_names(p.run()), ['notify-key', 'rotate-key'])

    def test_key_vault_key_set_rotation_policy_schema(self):
        for action in (
            {},
            {'lifetime_actions': []},
            {'expires_in': 'P1Y', 'lifetime_actions': [{'action': 'Rotate'}]},
            {'lifetime_actions': [{'action': 'Rotate', 'trigger': {}}]},
            {'expires_in': 'one year', 'lifetime_actions': [
                {'action': 'Rotate', 'trigger': {'time_after_create': 'P1D'}}]},
            {'lifetime_actions': [
                {'action': 'Rotate', 'trigger': {'time_before_expiry': '30 days'}}]},
            {'expires_in': 'P', 'lifetime_actions': [
                {'action': 'Rotate', 'trigger': {'time_after_create': 'P1D'}}]},
            {'lifetime_actions': [{'action': 'Delete', 'trigger': {'time_after_create': 'P1D'}}]},
            {'lifetime_actions': [{
                'action': 'Rotate',
                'trigger': {'time_after_create': 'P1D', 'time_before_expiry': 'P2D'}}]},
        ):
            with self.assertRaises(PolicyValidationError, msg=action):
                self.load_policy({
                    'name': 'test-key-vault-key-set-rotation-policy',
                    'resource': 'azure.keyvault-key',
                    'actions': [dict(action, type='set-rotation-policy')]
                }, validate=True)

    def test_key_vault_key_set_rotation_policy_action(self):
        p = self._rotation_policy('test-key-vault-key-set-rotation-policy', actions=[{
            'type': 'set-rotation-policy',
            'expires_in': 'P1Y',
            'lifetime_actions': [
                {'action': 'Rotate', 'trigger': {'time_before_expiry': 'P30D'}},
                {'action': 'Notify', 'trigger': {'time_after_create': 'P300D'}},
            ]
        }])
        resources = p.run()
        self.assertEqual(self._key_names(resources), ['notify-key'])

        client = p.resource_manager.get_client(vault_url='https://c7ntestvault.vault.azure.net')
        policy = client.get_key_rotation_policy('notify-key')
        self.assertEqual(policy.expires_in, 'P1Y')
        rotate, notify = policy.lifetime_actions
        self.assertEqual(rotate.action, KeyRotationPolicyAction.rotate)
        self.assertEqual(rotate.time_before_expiry, 'P30D')
        self.assertEqual(notify.action, KeyRotationPolicyAction.notify)
        self.assertEqual(notify.time_after_create, 'P300D')
        # The policy was read, updated with PUT and read back.
        self.assertTrue(self.cassette.all_played)

    def test_key_vault_key_set_rotation_policy_expires_in_only(self):
        p = self._rotation_policy('test-key-vault-key-set-rotation-policy-expires-in', actions=[
            {'type': 'set-rotation-policy', 'expires_in': 'P90D'}])
        p.run()

        client = p.resource_manager.get_client(vault_url='https://c7ntestvault.vault.azure.net')
        policy = client.get_key_rotation_policy('notify-key')
        self.assertEqual(policy.expires_in, 'P90D')
        # The lifetime actions of the current policy are kept.
        notify, = policy.lifetime_actions
        self.assertEqual(notify.action, KeyRotationPolicyAction.notify)
        self.assertTrue(self.cassette.all_played)
