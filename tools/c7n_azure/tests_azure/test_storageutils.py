# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from azure.mgmt.storage.models import StorageAccountListKeysResult, StorageAccountKey
from c7n_azure.session import Session
from c7n_azure.storage_utils import StorageUtilities
from mock import patch
from msrestazure.azure_cloud import AZURE_CHINA_CLOUD
from c7n.utils import local_session
from .azure_common import BaseTest, arm_template, requires_arm_polling

CHINA_STORAGE_ENDPOINT = AZURE_CHINA_CLOUD.suffixes.storage_endpoint
CHINA_STORAGE_ACCOUNT = "https://chinasa.blob" + CHINA_STORAGE_ENDPOINT


@requires_arm_polling
@pytest.mark.skiplive
class StorageUtilsTest(BaseTest):
    def setUp(self):
        super(StorageUtilsTest, self).setUp()
        self.session = Session()

    @arm_template('storage.json')
    def test_get_storage_client_by_uri(self):
        account = self.setup_account()
        url = "https://" + account.name + ".blob.core.windows.net/testcontainer/extrafolder"
        blob_service, container_name, key_prefix = \
            StorageUtilities.get_blob_client_by_uri(url, self.session)
        self.assertIsNotNone(blob_service)
        self.assertEqual(container_name, "testcontainer")
        self.assertEqual(key_prefix, "extrafolder")

    @arm_template('storage.json')
    def test_get_storage_client_by_uri_extra_directories(self):
        account = self.setup_account()
        url = "https://" + account.name + \
              ".blob.core.windows.net/testcontainer/extrafolder/foo/bar"
        blob_service, container_name, key_prefix = \
            StorageUtilities.get_blob_client_by_uri(url, self.session)
        self.assertIsNotNone(blob_service)
        self.assertEqual(container_name, "testcontainer")
        self.assertEqual(key_prefix, "extrafolder/foo/bar")

    @arm_template('storage.json')
    def test_get_queue_client_by_uri(self):
        account = self.setup_account()
        url = "https://" + account.name + ".queue.core.windows.net/testcc"
        queue_service, queue_name = StorageUtilities.get_queue_client_by_uri(url, self.session)
        self.assertIsNotNone(queue_service)
        self.assertEqual(queue_name, "testcc")

    @arm_template('storage.json')
    def test_create_delete_queue_from_storage_account(self):
        account = self.setup_account()
        queue_name = 'testqueuecc'

        queue = \
            StorageUtilities.create_queue_from_storage_account(account, queue_name, self.session)

        self.assertTrue(queue)

        result = \
            StorageUtilities.delete_queue_from_storage_account(account, queue_name, self.session)

        self.assertTrue(result)

    @arm_template('storage.json')
    @pytest.mark.skiplive
    def test_cycle_queue_message_by_uri(self):
        account = self.setup_account()
        url = "https://" + account.name + ".queue.core.windows.net/testcyclemessage"

        queue_settings = StorageUtilities.get_queue_client_by_uri(url, self.session)
        StorageUtilities.put_queue_message(*queue_settings, content=u"hello queue")

        # Pull messages, should be 1
        messages = StorageUtilities.get_queue_messages(*queue_settings)
        self.assertEqual(len(messages), 1)

        # Read message and delete it from queue
        for message in messages:
            self.assertEqual(message.content, u"hello queue")
            StorageUtilities.delete_queue_message(*queue_settings, message=message)

        # Pull messages again, should be empty
        messages = StorageUtilities.get_queue_messages(*queue_settings)
        self.assertEqual(len(messages), 0)

    def test_get_storage_primary_key(self):
        key1 = StorageAccountKey()
        key1.key_name = "key1"
        key1.value = "mock_storage_key"

        data = StorageAccountListKeysResult()
        data.keys = [key1]

        with patch(self._get_storage_client_string() + '.list_keys', return_value=data) \
                as list_keys_mock:
            primary_key = StorageUtilities.get_storage_primary_key(
                'mock_rg_group', 'mock_account', self.session)
            list_keys_mock.assert_called_with('mock_rg_group', 'mock_account', expand=None)
            self.assertEqual(primary_key, data.keys[0].value)

    def _get_storage_client_string(self):
        client = local_session(Session)\
            .client('azure.mgmt.storage.StorageManagementClient').storage_accounts
        return client.__module__ + '.' + client.__class__.__name__

    @patch('azure.storage.blob.BlobServiceClient.create_container')
    def test_get_blob_client_by_uri_china_cloud(self, mock_create):
        url = CHINA_STORAGE_ACCOUNT + "/testcontainer/extrafolder"
        blob_service, container_name, key_prefix = \
            StorageUtilities.get_blob_client_by_uri(url, Session(cloud_endpoints=AZURE_CHINA_CLOUD))
        self.assertIsNotNone(blob_service)
        self.assertEqual(container_name, "testcontainer")
        self.assertEqual(key_prefix, "extrafolder")
        self.assertTrue(CHINA_STORAGE_ENDPOINT in blob_service.primary_endpoint)
        self.assertTrue(mock_create.called_once())

    @patch('azure.storage.queue.QueueClient.create_queue')
    def test_get_queue_client_by_uri_china_cloud(self, mock_create):
        url = CHINA_STORAGE_ACCOUNT + "/queuename"
        queue_service, queue_name =\
            StorageUtilities.get_queue_client_by_uri(url,
                                                     Session(cloud_endpoints=AZURE_CHINA_CLOUD))
        self.assertIsNotNone(queue_service)
        self.assertEqual(queue_name, "queuename")
        self.assertIn(
            CHINA_STORAGE_ENDPOINT,
            queue_service._get_service(queue_name).primary_endpoint)
        self.assertTrue(mock_create.called_once())
