# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import namedtuple
from functools import lru_cache
from urllib.parse import urlparse

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient
from azure.storage.queue import QueueClient


class OldBlobServiceClient(BlobServiceClient):

    def create_blob_from_path(self, container_name, blob_name, path):
        client = self.get_blob_client(container_name, blob_name)
        with open(path, "rb") as data:
            client.upload_blob(data, overwrite=True)

    def get_blob_to_bytes(self, container_name, blob_name):
        client = self.get_blob_client(container_name, blob_name)
        return client.download_blob().content_as_bytes()

    def get_blob_to_path(self, container_name, blob_name, path):
        client = self.get_blob_client(container_name, blob_name)
        with open(path, "wb") as f:
            download_stream = client.download_blob()
            f.write(download_stream.readall())

    def create_blob_from_bytes(self, container_name, blob_name, content, validate_content):
        client = self.get_blob_client(container_name, blob_name)
        client.upload_blob(content, overwrite=True)

    def get_blob_properties(self, container_name, blob_name):
        client = self.get_blob_client(container_name, blob_name)
        return client.get_blob_properties()

    def list_blobs(self, container_name):
        client = self.get_container_client(container_name)
        return client.list_blobs()


class OldQueueService:

    def __init__(self, account_url, credential):
        self.account_url = account_url
        self.credential = credential
        self.clients = {}

    def create_queue(self, queue_name):
        queue_service = self._get_service(queue_name)
        try:
            queue_service.create_queue()
        except ResourceExistsError:
            # Queue already exists
            pass
        except Exception:
            return False
        return True

    def delete_queue(self, queue_name):
        queue_service = self._get_service(queue_name)
        try:
            queue_service.delete_queue()
        except Exception:
            return False
        return True

    def put_message(self, queue_name, content):
        queue_service = self._get_service(queue_name)
        return queue_service.send_message(content)

    def get_messages(self, queue_name, num_messages=None, visibility_timeout=None):
        queue_service = self._get_service(queue_name)
        messages = queue_service.receive_messages(number_of_messages=num_messages,
                                                  visibility_timeout=visibility_timeout)
        # This is an unexpected behavior of receive_messages function.
        # Seems like there is no way to specify maximum # of messages to retrieve,
        # so it will query the queue until it is empty..
        # With some busy queue it will lead to an infinite loop.
        # So we will query only first page of results and skip the rest as a workaround.
        try:
            return [m for m in messages.by_page().next()]
        except StopIteration:
            return []

    def delete_message(self, queue_name, message):
        queue_service = self._get_service(queue_name)
        queue_service.delete_message(message)

    def clear_messages(self, queue_name):
        queue_service = self._get_service(queue_name)
        queue_service.clear_messages()

    def _get_service(self, queue_name):
        return self.clients.get(queue_name, QueueClient(account_url=self.account_url,
                                                        queue_name=queue_name,
                                                        credential=self.credential))


class StorageUtilities:

    @staticmethod
    def get_blob_client_by_uri(storage_uri, session):
        storage = StorageUtilities.get_storage_from_uri(storage_uri)

        # Using our own wrapper to avoid major changes in existing code
        blob_service = OldBlobServiceClient(
            account_url=storage.account_url,
            credential=session.get_credentials()
        )
        try:
            blob_service.create_container(storage.container_name)
        except ResourceExistsError:
            # Container already exists
            pass

        return blob_service, storage.container_name, storage.file_prefix

    @staticmethod
    def get_queue_client_by_uri(queue_uri, session):
        storage = StorageUtilities.get_storage_from_uri(queue_uri)

        queue_service = OldQueueService(
            account_url=storage.account_url,
            credential=session.get_credentials()
        )
        queue_service.create_queue(storage.container_name)

        return queue_service, storage.container_name

    @staticmethod
    def get_queue_client_by_storage_account(storage_account, session):
        queue_service = OldQueueService(
            account_url=storage_account.primary_endpoints.queue,
            credential=session.get_credentials()
        )
        return queue_service

    @staticmethod
    def create_queue_from_storage_account(storage_account, name, session):
        queue_service = \
            StorageUtilities.get_queue_client_by_storage_account(storage_account, session)
        return queue_service.create_queue(name)

    @staticmethod
    def delete_queue_from_storage_account(storage_account, name, session):
        queue_service = \
            StorageUtilities.get_queue_client_by_storage_account(storage_account, session)
        return queue_service.delete_queue(name)

    @staticmethod
    def put_queue_message(queue_service, queue_name, content):
        return queue_service.put_message(queue_name, content)

    @staticmethod
    def get_queue_messages(queue_service, queue_name, num_messages=None, visibility_timeout=None):
        # Default message visibility timeout is 30 seconds
        # so you are expected to delete message within 30 seconds
        # if you have successfully processed it
        return queue_service.get_messages(queue_name,
                                          num_messages=num_messages,
                                          visibility_timeout=visibility_timeout)

    @staticmethod
    def delete_queue_message(queue_service, queue_name, message):
        queue_service.delete_message(queue_name, message)

    @staticmethod
    @lru_cache()
    def get_storage_primary_key(resource_group, name, session):
        storage_client = session.client('azure.mgmt.storage.StorageManagementClient')
        # TODO: Is this Expand required? Do we need to re-record some cassettes because of it?
        storage_keys = storage_client.storage_accounts.list_keys(resource_group, name, expand=None)
        return storage_keys.keys[0].value

    @staticmethod
    def get_storage_from_uri(storage_uri):
        parts = urlparse(storage_uri)
        account_url = 'https://{}'.format(parts.netloc)

        path_parts = parts.path.strip('/').split('/', 1)
        container_name = path_parts[0]
        if len(path_parts) > 1:
            prefix = path_parts[1]
        else:
            prefix = ""

        Storage = namedtuple('Storage', 'container_name, account_url, file_prefix')

        return Storage(
            container_name=container_name,
            account_url=account_url,
            file_prefix=prefix)
