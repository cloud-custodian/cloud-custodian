# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from azure.mgmt.storage.models import StorageAccountUpdateParameters
from c7n_azure.constants import BLOB_TYPE, FILE_TYPE, QUEUE_TYPE, TABLE_TYPE
from c7n_azure.resources.storage import StorageSettingsUtilities, StorageFirewallRulesFilter, \
    StorageFirewallBypassFilter
from c7n_azure.session import Session
from c7n_azure.storage_utils import StorageUtilities
from mock import patch, MagicMock, Mock
from netaddr import IPSet
from parameterized import parameterized

from c7n.utils import get_annotation_prefix
from c7n.utils import local_session
from ..azure_common import BaseTest, arm_template, cassette_name


class StorageTest(BaseTest):
    def setUp(self):
        super(StorageTest, self).setUp()
        StorageUtilities.get_storage_primary_key.cache_clear()

    def test_storage_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-storage',
                'resource': 'azure.storage'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('storage.json')
    def test_value_filter(self):
        p = self.load_policy({
            'name': 'test-azure-storage-enum',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_include(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'include': ['1.2.2.129']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_any(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'any': ['1.2.2.128/25', '8.8.8.8', '10.10.10.10']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_not_any(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'any': ['8.8.8.8', '10.10.10.10']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_not_only(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'only': ['1.2.2.128/25', '10.10.10.10']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_only(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'only': ['1.2.2.128/25', '3.1.1.1', '10.10.10.10']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_not_include_all_ranges(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'include': ['3.1.1.1', '3.1.1.2-3.1.1.2']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'include': ['1.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_not_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'include': ['2.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_equal(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'equal': ['3.1.1.1-3.1.1.1', '1.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_rules_not_equal(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-rules',
                 'equal': ['3.1.1.1-3.1.1.2', '3.1.1.1-3.1.1.1', '1.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @arm_template('storage.json')
    @cassette_name('firewall')
    def test_firewall_bypass(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccipstorage*'},
                {'type': 'firewall-bypass',
                 'mode': 'equal',
                 'list': ['AzureServices']}],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('storage.json')
    def test_diagnostic_settings_blob_storage_type(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'},
                {'type': 'storage-diagnostic-settings',
                 'storage-type': 'blob',
                 'key': 'logging.delete',
                 'value': False}],
        }, validate=True)

        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertTrue(get_annotation_prefix('blob') in resources[0])

    @arm_template('storage.json')
    def test_diagnostic_settings_file_storage_type(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'},
                {'type': 'storage-diagnostic-settings',
                 'storage-type': 'file',
                 'key': 'hour_metrics.enabled',
                 'value': True}],
        }, validate=True)

        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertTrue(get_annotation_prefix('file') in resources[0])

    @arm_template('storage.json')
    def test_diagnostic_settings_queue_storage_type(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'},
                {'type': 'storage-diagnostic-settings',
                 'storage-type': 'queue',
                 'key': 'logging.delete',
                 'value': False}],
        }, validate=True)

        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertTrue(get_annotation_prefix('queue') in resources[0])

    @arm_template('storage.json')
    def test_diagnostic_settings_table_storage_type(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'},
                {'type': 'storage-diagnostic-settings',
                 'storage-type': 'table',
                 'key': 'logging.delete',
                 'value': False}],
        }, validate=True)

        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertTrue(get_annotation_prefix('table') in resources[0])

    @arm_template('storage.json')
    def test_enable_log_settings(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cclgstorage*'}],
            'actions': [
                {
                    'type': 'set-log-settings',
                    'storage-types': ['blob', 'queue', 'table'],
                    'retention': 5,
                    'log': ['read', 'write', 'delete']
                }
            ]
        }, validate=True)

        resources = p.run()

        self.sleep_in_live_mode(30)

        session = local_session(p.session_factory)
        blob_settings = StorageSettingsUtilities.get_settings(
            BLOB_TYPE, resources[0], session=session)
        queue_settings = StorageSettingsUtilities.get_settings(
            QUEUE_TYPE, resources[0], session=session)
        table_settings = StorageSettingsUtilities.get_settings(
            TABLE_TYPE, resources[0], session=session)

        # assert all logging settings are enabled
        self.assertTrue(blob_settings['analytics_logging'].delete and
                        blob_settings['analytics_logging'].read and
                        blob_settings['analytics_logging'].write)
        self.assertTrue(queue_settings['analytics_logging'].delete and
                        queue_settings['analytics_logging'].read and
                        queue_settings['analytics_logging'].write)
        self.assertTrue(table_settings.logging.delete and
                        table_settings.logging.read and table_settings.logging.write)

        # assert retention policy is enabled
        self.assertTrue(blob_settings['analytics_logging'].retention_policy.enabled)
        self.assertTrue(queue_settings['analytics_logging'].retention_policy.enabled)
        self.assertTrue(table_settings.logging.retention_policy.enabled)

        # assert retention days is set to 5
        self.assertEqual(blob_settings['analytics_logging'].retention_policy.days, 5)
        self.assertEqual(queue_settings['analytics_logging'].retention_policy.days, 5)
        self.assertEqual(table_settings.logging.retention_policy.days, 5)

    @arm_template('storage.json')
    def test_disable_log_settings(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cclgstorage*'}],
            'actions': [
                {
                    'type': 'set-log-settings',
                    'storage-types': ['blob', 'queue', 'table'],
                    'retention': 5,
                    'log': ['delete']
                }
            ]
        }, validate=True)

        resources = p.run()

        self.sleep_in_live_mode(30)

        session = local_session(p.session_factory)
        blob_settings = StorageSettingsUtilities.get_settings(
            BLOB_TYPE, resources[0], session=session)
        queue_settings = StorageSettingsUtilities.get_settings(
            QUEUE_TYPE, resources[0], session=session)
        table_settings = StorageSettingsUtilities.get_settings(
            TABLE_TYPE, resources[0], session=session)

        # assert read and write logging settings are disabled
        self.assertFalse(blob_settings['analytics_logging'].read and
                         blob_settings['analytics_logging'].write)
        self.assertFalse(queue_settings['analytics_logging'].read and
                         queue_settings['analytics_logging'].write)
        self.assertFalse(table_settings.logging.read and
                         table_settings.logging.write)

        # assert delete logging settings are enabled
        self.assertTrue(blob_settings['analytics_logging'].delete)
        self.assertTrue(queue_settings['analytics_logging'].delete)
        self.assertTrue(table_settings.logging.delete)

    @arm_template('storage.json')
    @pytest.mark.skiplive
    def test_disable_retention_log_settings(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cclgstorage*'}],
            'actions': [
                {
                    'type': 'set-log-settings',
                    'storage-types': ['blob', 'queue', 'table'],
                    'retention': 0,
                    'log': ['read', 'write', 'delete']
                }
            ]
        }, validate=True)

        resources = p.run()
        session = local_session(p.session_factory)
        blob_settings = StorageSettingsUtilities.get_settings(
            BLOB_TYPE, resources[0], session=session)
        queue_settings = StorageSettingsUtilities.get_settings(
            QUEUE_TYPE, resources[0], session=session)
        table_settings = StorageSettingsUtilities.get_settings(
            TABLE_TYPE, resources[0], session=session)

        # assert retention policy is disabled
        print(blob_settings)
        self.assertFalse(blob_settings['analytics_logging'].retention_policy.enabled)
        self.assertFalse(queue_settings['analytics_logging'].retention_policy.enabled)
        self.assertFalse(table_settings.logging.retention_policy.enabled)

    @patch('azure.storage.blob.BlobServiceClient.get_service_properties')
    def test_storage_settings_get_blob_settings(self, mock_blob_properties_call):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account",
            "properties": {
                "primaryEndpoints": {
                    "blob": "https://cctstoragey6akyqpagdt3o.blob.core.windows.net/",
                    "queue": "https://cctstoragey6akyqpagdt3o.queue.core.windows.net/",
                    "table": "https://cctstoragey6akyqpagdt3o.table.core.windows.net/",
                    "file": "https://cctstoragey6akyqpagdt3o.file.core.windows.net/"
                },
            }
        }
        mock_session = MagicMock()
        StorageSettingsUtilities.get_settings(BLOB_TYPE, mock_storage_account, session=mock_session)
        mock_blob_properties_call.assert_called_once()

    @patch('azure.storage.file.FileService.get_file_service_properties')
    @patch('c7n_azure.storage_utils.StorageUtilities.get_storage_primary_key',
           return_value='mock_primary_key')
    def test_storage_settings_get_file_settings(self, mock_get_storage_key,
                                                mock_file_properties_call):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account",
            "properties": {
                "primaryEndpoints": {
                    "blob": "https://cctstoragey6akyqpagdt3o.blob.core.windows.net/",
                    "queue": "https://cctstoragey6akyqpagdt3o.queue.core.windows.net/",
                    "table": "https://cctstoragey6akyqpagdt3o.table.core.windows.net/",
                    "file": "https://cctstoragey6akyqpagdt3o.file.core.windows.net/"
                },
            }
        }
        mock_session = MagicMock()
        StorageSettingsUtilities.get_settings(FILE_TYPE, mock_storage_account, session=mock_session)
        mock_get_storage_key.assert_called_with(
            'mock_resource_group', 'mock_storage_account', mock_session)
        mock_file_properties_call.assert_called_once()

    @patch('azure.cosmosdb.table.tableservice.TableService.get_table_service_properties')
    @patch('c7n_azure.storage_utils.StorageUtilities.get_storage_primary_key',
           return_value='mock_primary_key')
    def test_storage_settings_get_table_settings(self, mock_get_storage_key,
                                                 mock_get_table_properties):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account",
            "properties": {
                "primaryEndpoints": {
                    "blob": "https://cctstoragey6akyqpagdt3o.blob.core.windows.net/",
                    "queue": "https://cctstoragey6akyqpagdt3o.queue.core.windows.net/",
                    "table": "https://cctstoragey6akyqpagdt3o.table.core.windows.net/",
                    "file": "https://cctstoragey6akyqpagdt3o.file.core.windows.net/"
                },
            }
        }
        mock_session = MagicMock()
        StorageSettingsUtilities.get_settings(
            TABLE_TYPE, mock_storage_account, session=mock_session)
        mock_get_storage_key.assert_called_with(
            'mock_resource_group', 'mock_storage_account', mock_session)
        mock_get_table_properties.assert_called_once()

    @patch('azure.storage.queue.QueueServiceClient.get_service_properties')
    def test_storage_settings_get_queue_settings(self, mock_get_queue_properties):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account",
            "properties": {
                "primaryEndpoints": {
                    "blob": "https://cctstoragey6akyqpagdt3o.blob.core.windows.net/",
                    "queue": "https://cctstoragey6akyqpagdt3o.queue.core.windows.net/",
                    "table": "https://cctstoragey6akyqpagdt3o.table.core.windows.net/",
                    "file": "https://cctstoragey6akyqpagdt3o.file.core.windows.net/"
                },
            }
        }
        mock_session = MagicMock()
        StorageSettingsUtilities.get_settings(
            QUEUE_TYPE, mock_storage_account, session=mock_session)
        mock_get_queue_properties.assert_called_once()

    @patch('azure.storage.queue.QueueServiceClient.set_service_properties')
    def test_storage_settings_update_logging_queue(self, mock_set_queue_properties):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account",
            "properties": {
                "primaryEndpoints": {
                    "blob": "https://cctstoragey6akyqpagdt3o.blob.core.windows.net/",
                    "queue": "https://cctstoragey6akyqpagdt3o.queue.core.windows.net/",
                    "table": "https://cctstoragey6akyqpagdt3o.table.core.windows.net/",
                    "file": "https://cctstoragey6akyqpagdt3o.file.core.windows.net/"
                },
            }
        }
        mock_session = MagicMock()
        log_settings = MagicMock()

        StorageSettingsUtilities.update_logging(
            QUEUE_TYPE, mock_storage_account, log_settings, session=mock_session)

        mock_set_queue_properties.assert_called_once()

    @patch('azure.cosmosdb.table.tableservice.TableService.set_table_service_properties')
    @patch('c7n_azure.storage_utils.StorageUtilities.get_storage_primary_key',
           return_value='mock_primary_key')
    def test_storage_settings_update_logging_table(self, mock_get_storage_key,
                                                   mock_set_table_properties):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account",
            "properties": {
                "primaryEndpoints": {
                    "blob": "https://cctstoragey6akyqpagdt3o.blob.core.windows.net/",
                    "queue": "https://cctstoragey6akyqpagdt3o.queue.core.windows.net/",
                    "table": "https://cctstoragey6akyqpagdt3o.table.core.windows.net/",
                    "file": "https://cctstoragey6akyqpagdt3o.file.core.windows.net/"
                },
            }
        }
        mock_session = MagicMock()
        log_settings = MagicMock()

        StorageSettingsUtilities.update_logging(
            TABLE_TYPE, mock_storage_account, log_settings, session=mock_session)

        mock_get_storage_key.assert_called_with(
            'mock_resource_group', 'mock_storage_account', mock_session)
        mock_set_table_properties.assert_called_once()

    @patch('azure.storage.blob.BlobServiceClient.set_service_properties')
    def test_storage_settings_update_logging_blob(self, mock_set_blob_properties):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account",
            "properties": {
                "primaryEndpoints": {
                    "blob": "https://cctstoragey6akyqpagdt3o.blob.core.windows.net/",
                    "queue": "https://cctstoragey6akyqpagdt3o.queue.core.windows.net/",
                    "table": "https://cctstoragey6akyqpagdt3o.table.core.windows.net/",
                    "file": "https://cctstoragey6akyqpagdt3o.file.core.windows.net/"
                },
            }
        }
        mock_session = MagicMock()
        log_settings = MagicMock()

        StorageSettingsUtilities.update_logging(
            BLOB_TYPE, mock_storage_account, log_settings, session=mock_session)

        mock_set_blob_properties.assert_called_once()

    def test_storage_settings_require_secure_transfer(self):
        with patch('azure.mgmt.storage.v%s.operations.'
        '_storage_accounts_operations.StorageAccountsOperations.update'
        % self._get_storage_management_client_api_string()) as update_storage_mock:
            p = self.load_policy({
                'name': 'my-first-policy',
                'resource': 'azure.storage',
                'filters': [
                    {'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctstorage*'}
                ],
                'actions': [
                    {'type': 'require-secure-transfer',
                    'value': True}
                ]
            })
            p.run()
            args = update_storage_mock.call_args_list[0][0]

            self.assertEqual(args[0], 'test_storage')
            self.assertTrue(args[1].startswith('cctstorage'))
            self.assertEqual(args[2],
                StorageAccountUpdateParameters(enable_https_traffic_only=True))

    def _get_storage_management_client_api_string(self):
        return local_session(Session)\
            .client('azure.mgmt.storage.StorageManagementClient')\
            .DEFAULT_API_VERSION.replace("-", "_")

    def test_storage_blob_services(self):
        p = self.load_policy({
            'name': 'test-azure-blob-services',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                'key': 'name',
                'op': 'glob',
                'value_type': 'normalize',
                'value': 'cctstorage*'},
                {'type': 'blob-services',
                 'key': 'deleteRetentionPolicy.enabled',
                 'value': True}],
        }, validate=True)

        resources = p.run()
        self.assertEqual(1, len(resources))

    def test_storage_management_policy_rules_filter(self):
        p = self.load_policy({
            'name': 'test-azure-mp-rules',
            'resource': 'azure.storage',
            'filters': [{
                'type': 'management-policy-rules',
                'attrs': [{
                    'type': 'value',
                    'key': 'definition.actions.baseBlob.delete.daysAfterModificationGreaterThan',
                    'value': 3,
                    'op': 'le'
                }]
            }]
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]['name'], 'cloudcustodiantest')
        self.assertEqual(len(resources[0]['c7n:management-policy-rules']), 1)
        self.assertEqual(resources[0]['c7n:management-policy-rules'][0]['name'], 'test')


class StorageFirewallFilterTest(BaseTest):

    def test_query_default_allow(self):
        resource = {'properties': {'networkAcls': {'defaultAction': 'Allow'}}}
        expected = IPSet(['0.0.0.0/0'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def test_query_default_deny(self):
        resource = {'properties': {'networkAcls': {'defaultAction': 'Deny',
                                                   'ipRules': [{'value': '10.0.0.0/16'},
                                                               {'value': '8.8.8.8'}]}}}
        expected = IPSet(['8.8.8.8', '10.0.0.0/16'])
        self.assertEqual(expected, self._get_filter()._query_rules(resource))

    def _get_filter(self, mode='equal'):
        data = {mode: ['10.0.0.0/8', '127.0.0.1']}
        return StorageFirewallRulesFilter(data, Mock())


class StorageFirewallBypassFilterTest(BaseTest):

    scenarios = [
        ['Allow', '', ['AzureServices', 'Metrics', 'Logging']],
        ['Deny', '', []],
        ['Deny', 'AzureServices', ['AzureServices']],
        ['Deny', 'AzureServices, Metrics, Logging', ['AzureServices', 'Metrics', 'Logging']]
    ]

    @parameterized.expand(scenarios)
    def test_run(self, default_action, bypass, expected):
        resource = {'properties': {'networkAcls': {'defaultAction': default_action,
                                                   'bypass': bypass}}}
        f = StorageFirewallBypassFilter({'mode': 'equal', 'list': []})
        self.assertEqual(expected, f._query_bypass(resource))
