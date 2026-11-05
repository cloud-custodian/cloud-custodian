# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from c7n.exceptions import PolicyExecutionError, PolicyValidationError

from ..azure_common import BaseTest, arm_template, strict_cassette


class DatabricksTest(BaseTest):
    def test_databricks_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-databricks',
                'resource': 'azure.databricks'
            }, validate=True)
            self.assertTrue(p)

    # Skip due to Azure Storage RBAC issues when databricks resource is deployed
    @arm_template('databricks.json')
    @pytest.mark.skiplive
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-databricks',
            'resource': 'azure.databricks',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'custodiandatabricks'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class DatabricksSetCmkEncryptionTest(BaseTest):

    key_vault_uri = 'https://cctestcmk.vault.azure.net/'
    action = {
        'type': 'set-cmk-encryption',
        'key-vault-uri': key_vault_uri,
        'key-name': 'cctest-dbfs-key',
    }

    def _load_policy(self, action):
        with self.sign_out_patch():
            return self.load_policy({
                'name': 'test-azure-databricks-cmk',
                'resource': 'azure.databricks',
                'actions': [action],
            }, validate=True)

    def _action(self, **options):
        return self._load_policy({**self.action, **options}).resource_manager.actions[0]

    def _workspace_properties(self):
        # Trimmed from the workspace GET in the recorded cassette.
        return {
            'managedResourceGroupId': '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47'
                                      '/resourceGroups/test_databricks-cmk_managed',
            'parameters': {
                'enableNoPublicIp': {'type': 'Bool', 'value': True},
                'prepareEncryption': {'type': 'Bool', 'value': True},
                'storageAccountName': {'type': 'String', 'value': 'dbstoragecctest'},
            },
        }

    def test_schema_requires_key_name(self):
        action = {k: v for k, v in self.action.items() if k != 'key-name'}

        with pytest.raises(PolicyValidationError, match="'key-name' is a required property"):
            self._load_policy(action)

    def test_set_key_adds_encryption_and_keeps_the_rest(self):
        properties = self._workspace_properties()

        self._action().set_key(properties)

        expected = self._workspace_properties()
        expected['parameters']['encryption'] = {
            'value': {
                'keySource': 'Microsoft.Keyvault',
                'keyvaulturi': self.key_vault_uri,
                'KeyName': 'cctest-dbfs-key',
            }
        }
        assert properties == expected

    def test_set_key_with_key_version(self):
        properties = self._workspace_properties()

        self._action(**{'key-version': 'abc123'}).set_key(properties)

        assert properties['parameters']['encryption']['value']['keyversion'] == 'abc123'

    def test_unexpanded_key_vault_uri_stops_the_run(self):
        action = self._action(**{'key-vault-uri': '{databricks_cmk_key_vault_uri}'})

        with pytest.raises(PolicyExecutionError, match='must start with https://'):
            action.process([])

    def test_unprepared_workspaces_are_skipped(self):
        workspaces = [
            {
                'name': 'cctest-unprepared',
                'properties': {'parameters': {'prepareEncryption': {'value': False}}},
            },
            {'name': 'cctest-no-parameters', 'properties': {}},
        ]

        with self.sign_out_patch():
            with self.assertLogs('custodian.azure.AzureBaseAction', level='WARNING') as logs:
                assert self._action().process(workspaces) == []

        assert len(logs.output) == 1
        assert 'implicitly filtered 0 of 2' in logs.output[0]

    def test_failure_does_not_stop_other_workspaces(self):
        prepared = {'properties': {'parameters': {'prepareEncryption': {'value': True}}}}
        workspaces_without_ids = [
            {'name': 'cctest-no-id-1', **prepared},
            {'name': 'cctest-no-id-2', **prepared},
        ]

        with self.sign_out_patch():
            with self.assertLogs('custodian.azure.AzureBaseAction', level='ERROR') as logs:
                with pytest.raises(KeyError):
                    self._action().process(workspaces_without_ids)

        assert any("'cctest-no-id-1'" in line for line in logs.output)
        assert any("'cctest-no-id-2'" in line for line in logs.output)

    @arm_template('databricks-cmk.json')
    @strict_cassette('databricks-cmk-encryption')
    def test_set_cmk_encryption_sets_the_key(self):
        vaults = self.session.client('azure.mgmt.keyvault.KeyVaultManagementClient').vaults
        [vault] = vaults.list_by_resource_group('test_databricks-cmk')
        p = self.load_policy({
            'name': 'test-azure-databricks-cmk',
            'resource': 'azure.databricks',
            'filters': [{'name': 'cctestdatabrickscmk'}],
            'actions': [{
                'type': 'set-cmk-encryption',
                'key-vault-uri': vault.properties.vault_uri,
                'key-name': 'cctest-dbfs-key',
            }],
        })

        resources = p.run()

        assert [r['name'] for r in resources] == ['cctestdatabrickscmk']
        client = self.session.client('azure.mgmt.databricks.DatabricksClient')
        workspace = client.workspaces.get('test_databricks-cmk', 'cctestdatabrickscmk')
        key = workspace.parameters.encryption.value
        assert key.key_source == 'Microsoft.Keyvault'
        assert key.key_vault_uri == vault.properties.vault_uri
        assert key.key_name == 'cctest-dbfs-key'
        assert workspace.parameters.prepare_encryption.value is True
        assert workspace.sku.name == 'premium'
