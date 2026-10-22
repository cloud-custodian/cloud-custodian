# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
from unittest import mock

from parameterized import parameterized

from c7n import exceptions

from ..azure_common import BaseTest, arm_template, strict_cassette


class StorageUpdateSchemaTest(BaseTest):

    @parameterized.expand([
        ('defaultToOAuthAuthentication', False),
        ('supportsHttpsTrafficOnly', True),
        ('allowBlobPublicAccess', False),
        ('allowSharedKeyAccess', False),
        ('allowCrossTenantReplication', False),
        ('isLocalUserEnabled', False),
        ('isSftpEnabled', False),
        ('minimumTlsVersion', 'TLS1_2'),
        ('publicNetworkAccess', 'Disabled'),
        ('accessTier', 'Cold'),
        ('allowedCopyScope', None),
    ])
    def test_update_schema(self, field: str, value: object) -> None:
        with self.sign_out_patch():
            policy = self.load_policy({
                'name': 'storage-update',
                'resource': 'azure.storage',
                'actions': [{
                    'type': 'update',
                    'properties': {field: value},
                }],
            }, validate=True)
        self.assertTrue(policy)

    @parameterized.expand([
        ('missing', {}),
        ('empty', {'properties': {}}),
        ('unknown', {'properties': {'defaultToOauthAuthentication': True}}),
        ('wrong_type', {'properties': {'defaultToOAuthAuthentication': 'true'}}),
        ('null_boolean', {'properties': {'defaultToOAuthAuthentication': None}}),
        ('unsupported_tls', {'properties': {'minimumTlsVersion': 'TLS1_3'}}),
        ('invalid_network', {'properties': {'publicNetworkAccess': 'Allow'}}),
        ('invalid_tier', {'properties': {'accessTier': 'Premium'}}),
        ('invalid_copy_scope', {'properties': {'allowedCopyScope': 'Any'}}),
        ('read_only', {'properties': {'provisioningState': 'Succeeded'}}),
        ('creation_only', {'properties': {'isHnsEnabled': True}}),
        ('encryption', {'properties': {'encryption': {'keySource': 'Microsoft.Storage'}}}),
        ('nested', {'properties': {'networkAcls': {'defaultAction': 'Deny'}}}),
        ('identity', {'identity': {'type': 'SystemAssigned'}}),
    ])
    def test_update_schema_rejects_invalid(self, name: str, fields: dict) -> None:
        with self.sign_out_patch(), self.assertRaises(exceptions.PolicyValidationError):
            self.load_policy({
                'name': 'storage-update',
                'resource': 'azure.storage',
                'actions': [{'type': 'update', **fields}],
            }, validate=True)

    def test_update_request_preserves_false_and_null(self) -> None:
        with self.sign_out_patch():
            policy = self.load_policy({
                'name': 'storage-update',
                'resource': 'azure.storage',
                'actions': [{
                    'type': 'update',
                    'properties': {
                        'defaultToOAuthAuthentication': False,
                        'allowedCopyScope': None,
                    },
                }],
            }, validate=True)
        action = policy.resource_manager.actions[0]
        with mock.patch.object(policy.resource_manager, 'get_client') as get_client:
            action._prepare_processing()
            action._process_resource({
                'resourceGroup': 'test_storage-update',
                'name': 'test-account',
                'properties': {'minimumTlsVersion': 'TLS1_2'},
            })
        update = get_client.return_value.storage_accounts.update
        update.assert_called_once()
        group, name, body = update.call_args.args
        self.assertEqual(group, 'test_storage-update')
        self.assertEqual(name, 'test-account')
        self.assertEqual(json.loads(body), {
            'properties': {
                'defaultToOAuthAuthentication': False,
                'allowedCopyScope': None,
            },
        })


class StorageUpdateTest(BaseTest):
    recording_resource_group = 'test_storage-update'

    @arm_template('storage-update.json')
    @strict_cassette('update_oauth_default')
    def test_update_oauth_default(self) -> None:
        policy_data = {
            'name': 'storage-default-to-entra-authorization',
            'resource': 'azure.storage',
            'filters': [
                {'resourceGroup': self.recording_resource_group},
                {'tag:c7n-test': 'storage-update'},
                {'or': [
                    {'properties.defaultToOAuthAuthentication': 'absent'},
                    {'properties.defaultToOAuthAuthentication': False},
                ]},
            ],
            'actions': [{
                'type': 'update',
                'properties': {'defaultToOAuthAuthentication': True},
            }],
        }
        inventory = self.load_policy({
            'name': 'storage-update-inventory',
            'resource': 'azure.storage',
            'filters': policy_data['filters'][:2],
        }).run()
        self.assertEqual(len(inventory), 2)
        scalar = next(r for r in inventory if r['tags']['role'] == 'scalar')
        hns = next(r for r in inventory if r['tags']['role'] == 'hns')
        self.assertNotIn('defaultToOAuthAuthentication', scalar['properties'])
        self.assertTrue(hns['properties']['defaultToOAuthAuthentication'])
        policy = self.load_policy(policy_data)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        resource = resources[0]
        self.assertEqual(resource['id'], scalar['id'])
        client = policy.resource_manager.get_client()
        account = client.storage_accounts.get_properties(
            resource['resourceGroup'],
            resource['name'],
        )
        self.assertTrue(account.default_to_o_auth_authentication)
        self.assertEqual(self.load_policy(policy_data).run(), [])

        policy = self.load_policy({
            'name': 'storage-default-to-shared-key',
            'resource': 'azure.storage',
            'filters': [{'id': resource['id']}],
            'actions': [{
                'type': 'update',
                'properties': {'defaultToOAuthAuthentication': False},
            }],
        })
        self.assertEqual(len(policy.run()), 1)
        account = client.storage_accounts.get_properties(
            resource['resourceGroup'],
            resource['name'],
        )
        self.assertFalse(account.default_to_o_auth_authentication)

    @parameterized.expand([
        ('supportsHttpsTrafficOnly', [False, True], 'scalar'),
        ('allowBlobPublicAccess', [True, False], 'scalar'),
        ('allowSharedKeyAccess', [False, True], 'scalar'),
        ('allowCrossTenantReplication', [True, False], 'scalar'),
        ('isLocalUserEnabled', [True, False], 'scalar'),
        ('isSftpEnabled', [True, False], 'hns'),
        ('minimumTlsVersion', ['TLS1_0', 'TLS1_1', 'TLS1_2'], 'scalar'),
        ('publicNetworkAccess', ['Disabled', 'SecuredByPerimeter', 'Enabled'], 'scalar'),
        ('accessTier', ['Cool', 'Cold', 'Hot'], 'scalar'),
        ('allowedCopyScope', ['AAD', 'PrivateLink', None], 'scalar'),
    ])
    @arm_template('storage-update.json')
    @strict_cassette(None)
    def test_update_property(self, field: str, values: list, role: str) -> None:
        for value in values:
            policy = self.load_policy({
                'name': 'storage-update-property',
                'resource': 'azure.storage',
                'filters': [
                    {'resourceGroup': self.recording_resource_group},
                    {'tag:c7n-test': 'storage-update'},
                    {'tag:role': role},
                ],
                'actions': [{
                    'type': 'update',
                    'properties': {field: value},
                }],
            })
            resources = policy.run()
            self.assertEqual(len(resources), 1)
            resource = resources[0]
            client = policy.resource_manager.get_client()
            account = client.storage_accounts.get_properties(
                resource['resourceGroup'],
                resource['name'],
            ).serialize(keep_readonly=True)
            self.assertEqual(account['properties'].get(field), value)
            self.assertEqual(
                account['properties'].get('defaultToOAuthAuthentication'),
                resource['properties'].get('defaultToOAuthAuthentication'),
            )
