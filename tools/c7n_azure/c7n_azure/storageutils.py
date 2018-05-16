# Copyright 2018 Capital One Services, LLC
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

from c7n.utils import local_session
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser


class StorageUtilities(object):

    @staticmethod
    def get_storage_account_by_name(storage_account_name):
        s = local_session(Session)
        client = s.client('azure.mgmt.storage.StorageManagementClient')
        accounts = list(client.storage_accounts.list())
        matching_account = [a for a in accounts if a.name == storage_account_name]
        if not matching_account:
            return None

        return matching_account[0]

    @staticmethod
    def get_storage_keys(storage_account_id):
        s = local_session(Session)
        client = s.client('azure.mgmt.storage.StorageManagementClient')
        resource_group = ResourceIdParser.get_resource_group(storage_account_id)
        resource_name = ResourceIdParser.get_resource_name(storage_account_id)
        keys = client.storage_accounts.list_keys(resource_group, resource_name)
        return keys.keys
