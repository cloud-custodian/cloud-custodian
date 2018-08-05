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

from collections import namedtuple

from azure.storage.blob import BlockBlobService
from azure.storage.queue import QueueService
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser
from six.moves.urllib.parse import urlparse

from c7n.utils import local_session

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache


class StorageUtilities(object):

    @staticmethod
    def get_blob_client_by_uri(storage_uri, session=None):
        storage = StorageUtilities.get_storage_from_uri(storage_uri, session)

        blob_service = BlockBlobService(account_name=storage.storage_name, account_key=storage.key)
        blob_service.create_container(storage.container_name)
        return blob_service, storage.container_name, storage.file_prefix

    @staticmethod
    def get_queue_client_by_uri(queue_uri, session=None):
        storage = StorageUtilities.get_storage_from_uri(queue_uri, session)

        queue_service = QueueService(account_name=storage.storage_name, account_key=storage.key)
        queue_service.create_queue(storage.container_name)

        return queue_service, storage.container_name

    @staticmethod
    def put_queue_message(queue_service, queue_name, content):
        return queue_service.put_message(queue_name, content)

    @staticmethod
    def get_queue_messages(queue_service, queue_name, num_messages=None):
        # Default message visibility timeout is 30 seconds
        # so you are expected to delete message within 30 seconds
        # if you have successfully processed it
        return queue_service.get_messages(queue_name, num_messages)

    @staticmethod
    def delete_queue_message(queue_service, queue_name, message):
        queue_service.delete_message(queue_name, message.id, message.pop_receipt)

    @staticmethod
    def get_storage_account_by_name(storage_account_name, session=None):
        s = session or local_session(Session)
        client = s.client('azure.mgmt.storage.StorageManagementClient')
        accounts = list(client.storage_accounts.list())
        matching_account = [a for a in accounts if a.name == storage_account_name]
        if not matching_account:
            return None

        return matching_account[0]

    @staticmethod
    def get_storage_keys(storage_account_id, session=None):
        s = session or local_session(Session)
        client = s.client('azure.mgmt.storage.StorageManagementClient')
        resource_group = ResourceIdParser.get_resource_group(storage_account_id)
        resource_name = ResourceIdParser.get_resource_name(storage_account_id)
        keys = client.storage_accounts.list_keys(resource_group, resource_name)
        return keys.keys

    @staticmethod
    @lru_cache()
    def get_storage_from_uri(storage_uri, session=None):
        parts = urlparse(storage_uri)
        storage_name = str(parts.netloc).partition('.')[0]

        path_parts = parts.path.strip('/').split('/', 1)
        container_name = path_parts[0]
        if len(path_parts) > 1:
            prefix = path_parts[1]
        else:
            prefix = ""

        account = StorageUtilities.get_storage_account_by_name(storage_name, session)
        key = StorageUtilities.get_storage_keys(account.id, session)[0].value

        Storage = namedtuple('Storage', 'container_name, storage_name, key, file_prefix')

        return Storage(
            container_name=container_name,
            storage_name=storage_name,
            key=key,
            file_prefix=prefix)
