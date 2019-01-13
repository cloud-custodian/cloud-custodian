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

from azure.storage.common import TokenCredential
from azure.storage.blob import BlockBlobService
from azure.storage.queue import QueueService
from c7n_azure.constants import RESOURCE_STORAGE
from six.moves.urllib.parse import urlparse

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache


class StorageUtilities(object):

    @staticmethod
    def get_blob_client_by_uri(storage_uri, session):
        storage = StorageUtilities.get_storage_from_uri(storage_uri, session)

        blob_service = BlockBlobService(
            account_name=storage.storage_name,
            token_credential=storage.token)
        blob_service.create_container(storage.container_name)
        return blob_service, storage.container_name, storage.file_prefix

    @staticmethod
    def get_blob_client_from_storage_account(resource_group, name, session, sas_generation=False):
        storage_client = session.client('azure.mgmt.storage.StorageManagementClient')
        storage_account = storage_client.storage_accounts.get_properties(resource_group, name)

        # sas tokens can only be generated from clients created from account keys
        primary_key = token = None
        if sas_generation:
            storage_keys = storage_client.storage_accounts.list_keys(resource_group, name)
            primary_key = storage_keys.keys[0].value
        else:
            token = StorageUtilities.get_storage_token(session)

        return BlockBlobService(
            account_name=storage_account.name,
            account_key=primary_key,
            token_credential=token
        )

    @staticmethod
    def get_queue_client_by_uri(queue_uri, session):
        storage = StorageUtilities.get_storage_from_uri(queue_uri, session)

        queue_service = QueueService(
            account_name=storage.storage_name,
            token_credential=storage.token)
        queue_service.create_queue(storage.container_name)

        return queue_service, storage.container_name

    @staticmethod
    def create_queue_from_storage_account(storage_account, name, session):
        token = StorageUtilities.get_storage_token(session)
        queue_service = QueueService(
            account_name=storage_account.name,
            token_credential=token)
        return queue_service.create_queue(name)

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
    def get_storage_token(session):
        if session.resource_namespace != RESOURCE_STORAGE:
            session = session.get_session_for_resource(RESOURCE_STORAGE)
        return TokenCredential(session.get_bearer_token())

    @staticmethod
    @lru_cache()
    def get_storage_from_uri(storage_uri, session):
        parts = urlparse(storage_uri)
        storage_name = str(parts.netloc).partition('.')[0]

        path_parts = parts.path.strip('/').split('/', 1)
        container_name = path_parts[0]
        if len(path_parts) > 1:
            prefix = path_parts[1]
        else:
            prefix = ""

        token = StorageUtilities.get_storage_token(session)

        Storage = namedtuple('Storage', 'container_name, storage_name, token, file_prefix')

        return Storage(
            container_name=container_name,
            storage_name=storage_name,
            token=token,
            file_prefix=prefix)
