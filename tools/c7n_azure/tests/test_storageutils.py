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
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.session import Session


class StorageUtilsTest(BaseTest):
    def setUp(self):
        super(StorageUtilsTest, self).setUp()

    def setup_account(self):
        # Find actual name of storage account provisioned in our test environment
        s = Session()
        client = s.client('azure.mgmt.storage.StorageManagementClient')
        accounts = list(client.storage_accounts.list())
        matching_account = [a for a in accounts if a.name.startswith("cctstorage")]
        return matching_account[0]

    @arm_template('storage.json')
    def test_get_storage_client_by_uri(self):
        account = self.setup_account()
        url = "https://" + account.name + ".blob.core.windows.net/testcontainer"
        blob_service, container_name = StorageUtilities.get_blob_client_by_uri(url)
        self.assertIsNotNone(blob_service)
        self.assertIsNotNone(container_name)

    @arm_template('storage.json')
    def test_get_queue_client_by_uri(self):
        account = self.setup_account()
        url = "https://" + account.name + ".queue.core.windows.net/testcc"
        queue_service, queue_name = StorageUtilities.get_queue_client_by_uri(url)
        self.assertIsNotNone(queue_service)
        self.assertIsNotNone(queue_name)

    @arm_template('storage.json')
    def test_cycle_queue_message_by_uri(self):
        account = self.setup_account()
        url = "https://" + account.name + ".queue.core.windows.net/testcyclemessage"

        queue_settings = StorageUtilities.get_queue_client_by_uri(url)
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

    @arm_template('storage.json')
    def test_get_account_by_name(self):
        account = self.setup_account()
        found = StorageUtilities.get_storage_account_by_name(account.name)
        self.assertEqual(found.id, account.id)

    @arm_template('storage.json')
    def test_get_account_by_name_not_exists(self):
        account = self.setup_account()
        found = StorageUtilities.get_storage_account_by_name(account.name + "break")
        self.assertIsNone(found)

    @arm_template('storage.json')
    def test_get_keys(self):
        account = self.setup_account()
        keys = StorageUtilities.get_storage_keys(account.id)
        self.assertEqual(len(keys), 2)
