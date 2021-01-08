# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import namedtuple
from functools import wraps
from urllib.parse import urlparse

from azure.common import AzureHttpError
from azure.storage.common import TokenCredential
from azure.storage.blob import BlockBlobService
from azure.storage.queue import QueueService
from c7n_azure.constants import RESOURCE_STORAGE

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache


class StorageUtilities:

    class Decorators:
        @staticmethod
        def handle_token_failure(func):
            @wraps(func)
            def wrapper(*a, **kw):
                try:
                    return func(*a, **kw)
                except AzureHttpError as e:
                    if e.error_code == 'AuthenticationFailed':
                        StorageUtilities.get_storage_from_uri.cache_clear()
                        StorageUtilities.get_storage_token.cache_clear()
                        StorageUtilities.get_storage_primary_key.cache_clear()
                        return func(*a, **kw)
                    else:
                        raise e
            return wrapper

    @staticmethod
    @Decorators.handle_token_failure
    def get_blob_client_by_uri(storage_uri, session):
        storage = StorageUtilities.get_storage_from_uri(storage_uri, session)

        blob_service = BlockBlobService(
            account_name=storage.storage_name,
            token_credential=storage.token)
        blob_service.create_container(storage.container_name)
        return blob_service, storage.container_name, storage.file_prefix

    @staticmethod
    @Decorators.handle_token_failure
    def get_blob_client_from_storage_account(resource_group, name, session, sas_generation=False):
        # sas tokens can only be generated from clients created from account keys
        primary_key = token = None
        if sas_generation:
            primary_key = StorageUtilities.get_storage_primary_key(resource_group, name, session)
        else:
            token = StorageUtilities.get_storage_token(session)

        return BlockBlobService(
            account_name=name,
            account_key=primary_key,
            token_credential=token
        )

    @staticmethod
    @Decorators.handle_token_failure
    def get_queue_client_by_uri(queue_uri, session):
        storage = StorageUtilities.get_storage_from_uri(queue_uri, session)

        queue_service = QueueService(
            account_name=storage.storage_name,
            token_credential=storage.token)
        queue_service.create_queue(storage.container_name)

        return queue_service, storage.container_name

    @staticmethod
    @Decorators.handle_token_failure
    def get_queue_client_by_storage_account(storage_account, session):
        token = StorageUtilities.get_storage_token(session)
        queue_service = QueueService(
            account_name=storage_account.name,
            token_credential=token)
        return queue_service

    @staticmethod
    @Decorators.handle_token_failure
    def create_queue_from_storage_account(storage_account, name, session):
        token = StorageUtilities.get_storage_token(session)

        queue_service = QueueService(
            account_name=storage_account.name,
            token_credential=token)
        return queue_service.create_queue(name)

    @staticmethod
    @Decorators.handle_token_failure
    def delete_queue_from_storage_account(storage_account, name, session):
        token = StorageUtilities.get_storage_token(session)
        queue_service = QueueService(
            account_name=storage_account.name,
            token_credential=token)
        return queue_service.delete_queue(name)

    @staticmethod
    @Decorators.handle_token_failure
    def put_queue_message(queue_service, queue_name, content):
        return queue_service.put_message(queue_name, content)

    @staticmethod
    @Decorators.handle_token_failure
    def get_queue_messages(queue_service, queue_name, num_messages=None, visibility_timeout=None):
        # Default message visibility timeout is 30 seconds
        # so you are expected to delete message within 30 seconds
        # if you have successfully processed it
        return queue_service.get_messages(queue_name,
                                          num_messages=num_messages,
                                          visibility_timeout=visibility_timeout)

    @staticmethod
    @Decorators.handle_token_failure
    def delete_queue_message(queue_service, queue_name, message):
        queue_service.delete_message(queue_name, message.id, message.pop_receipt)

    @staticmethod
    @lru_cache()
    def get_storage_token(session):
        if session.resource_namespace != RESOURCE_STORAGE:
            session = session.get_session_for_resource(RESOURCE_STORAGE)
        return TokenCredential(session.get_bearer_token())

    @staticmethod
    @lru_cache()
    def get_storage_primary_key(resource_group, name, session):
        storage_client = session.client('azure.mgmt.storage.StorageManagementClient')
        storage_keys = storage_client.storage_accounts.list_keys(resource_group, name)
        return storage_keys.keys[0].value

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
