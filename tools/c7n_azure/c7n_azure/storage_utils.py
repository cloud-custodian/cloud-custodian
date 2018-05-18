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

from azure.storage.queue import QueueService
from azure.storage.blob import BlockBlobService
from six.moves.urllib.parse import urlparse

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache


class StorageUtilities(object):

    @staticmethod
    def get_blob_client_by_uri(storage_uri):
        container_name, storage_name, key = StorageUtilities.get_storage_from_uri(storage_uri)

        blob_service = BlockBlobService(account_name=storage_name, account_key=key)
        blob_service.create_container(container_name)

        return blob_service, container_name

    @staticmethod
    def get_queue_client_by_uri(queue_uri):
        queue_name, storage_name, key = StorageUtilities.get_storage_from_uri(queue_uri)

        queue_service = QueueService(account_name=storage_name, account_key=key)
        queue_service.create_queue(queue_name)

        return queue_service, queue_name

    @staticmethod
    def put_queue_message(queue_service, queue_name, content):
        queue_service.put_message(queue_name, content)

    @staticmethod
    def get_queue_messages(queue_service, queue_name):
        # Default message visibility timeout is 30 seconds
        # so you are expected to delete message within 30 seconds
        # if you have successfully processed it
        return queue_service.get_messages(queue_name)

    @staticmethod
    def delete_queue_message(queue_service, queue_name, message):
        queue_service.delete_message(queue_name, message.id, message.pop_receipt)

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

    @staticmethod
    @lru_cache()
    def get_storage_from_uri(storage_uri):
        parts = urlparse(storage_uri)
        storage_name = str(parts.netloc).partition('.')[0]
        container_name = parts.path.partition('/')[2]
        account = StorageUtilities.get_storage_account_by_name(storage_name)
        key = StorageUtilities.get_storage_keys(account.id)[0].value
        return container_name, storage_name, key
