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
from c7n_azure.storageutils import StorageUtilities
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

