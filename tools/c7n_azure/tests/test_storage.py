# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest, arm_template
from c7n_azure.resources.storage import StorageSettingsUtilities
from mock import patch, MagicMock

from c7n.utils import get_annotation_prefix


class StorageTest(BaseTest):
    def setUp(self):
        super(StorageTest, self).setUp()

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
                 'include': ['3.1.1.1']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('storage.json')
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

    @patch('azure.storage.blob.blockblobservice.BlockBlobService.get_blob_service_properties')
    def test_storage_settings_get_blob_settings(self, mock_blob_properties_call):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account"
        }
        mock_token = 'mock_token'
        StorageSettingsUtilities.get_blob_settings(mock_storage_account, mock_token)
        mock_blob_properties_call.assert_called_once()

    @patch('azure.storage.file.fileservice.FileService.get_file_service_properties')
    @patch('c7n_azure.storage_utils.StorageUtilities.get_storage_primary_key',
           return_value='mock_primary_key')
    def test_storage_settings_get_file_settings(self, mock_get_storage_key,
                                                mock_file_properties_call):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account"
        }
        mock_session = MagicMock()
        StorageSettingsUtilities.get_file_settings(mock_storage_account, mock_session)
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
            "name": "mock_storage_account"
        }
        mock_session = MagicMock()
        StorageSettingsUtilities.get_table_settings(mock_storage_account, mock_session)
        mock_get_storage_key.assert_called_with(
            'mock_resource_group', 'mock_storage_account', mock_session)
        mock_get_table_properties.assert_called_once()

    @patch('azure.storage.queue.queueservice.QueueService.get_queue_service_properties')
    def test_storage_settings_get_queue_settings(self, mock_get_queue_properties):
        mock_storage_account = {
            "resourceGroup": "mock_resource_group",
            "name": "mock_storage_account"
        }
        mock_token = 'mock_token'
        StorageSettingsUtilities.get_queue_settings(mock_storage_account, mock_token)
        mock_get_queue_properties.assert_called_once()
