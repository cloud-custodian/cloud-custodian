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

import logging
from concurrent.futures import as_completed

from azure.cosmosdb.table import TableService
from azure.mgmt.storage.models import IPRule, \
    NetworkRuleSet, StorageAccountUpdateParameters, VirtualNetworkRule
from azure.storage.blob import BlockBlobService
from azure.storage.file import FileService
from azure.storage.queue import QueueService
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.filters import FirewallRulesFilter, ValueFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.storage_utils import StorageUtilities
from netaddr import IPNetwork

# from azure.storage.blob import BaseBlobService
from c7n.filters.core import type_schema
from c7n.utils import chunks
from c7n.utils import local_session

import jsonpickle
import json


@resources.register('storage')
class Storage(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.storage'
        client = 'StorageManagementClient'
        enum_spec = ('storage_accounts', 'list', None)
        diagnostic_settings_enabled = False
        resource_type = 'Microsoft.Storage/storageAccounts'


@Storage.action_registry.register('set-network-rules')
class StorageSetNetworkRulesAction(AzureBaseAction):

    schema = type_schema(
        'set-network-rules',
        required=['default-action'],
        **{
            'default-action': {'enum': ['Allow', 'Deny']},
            'bypass': {'type': 'array', 'items': {'enum': ['AzureServices', 'Logging', 'Metrics']}},
            'ip-rules': {
                'type': 'array',
                'items': {'ip-address-or-range': {'type': 'string'}}
            },
            'virtual-network-rules': {
                'type': 'array',
                'items': {'virtual-network-resource-id': {'type': 'string'}}
            }
        }
    )

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        rule_set = NetworkRuleSet(default_action=self.data['default-action'])

        if 'ip-rules' in self.data:
            rule_set.ip_rules = [
                IPRule(
                    ip_address_or_range=r['ip-address-or-range'],
                    action='Allow')  # 'Allow' is the only allowed action
                for r in self.data['ip-rules']]

        if 'virtual-network-rules' in self.data:
            rule_set.virtual_network_rules = [
                VirtualNetworkRule(
                    virtual_network_resource_id=r['virtual-network-resource-id'],
                    action='Allow')  # 'Allow' is the only allowed action
                for r in self.data['virtual-network-rules']]

        if len(self.data.get('bypass', [])) > 0:
            rule_set.bypass = ','.join(self.data['bypass'])
        else:
            rule_set.bypass = 'None'

        self.client.storage_accounts.update(
            resource['resourceGroup'],
            resource['name'],
            StorageAccountUpdateParameters(network_rule_set=rule_set))


@Storage.filter_registry.register('firewall-rules')
class StorageFirewallRulesFilter(FirewallRulesFilter):

    def __init__(self, data, manager=None):
        super(StorageFirewallRulesFilter, self).__init__(data, manager)
        self._log = logging.getLogger('custodian.azure.storage')

    @property
    def log(self):
        return self._log

    def _query_rules(self, resource):

        ip_rules = resource['properties']['networkAcls']['ipRules']

        resource_rules = set([IPNetwork(r['value']) for r in ip_rules])

        return resource_rules


@Storage.filter_registry.register('storage-diagnostic-settings')
class StorageDiagnosticSettingsFilter(ValueFilter):
    BLOB_TYPE = 'blob'
    QUEUE_TYPE = 'queue'
    TABLE_TYPE = 'table'
    FILE_TYPE = 'file'

    def __init__(self, data, manager=None):
        super(StorageDiagnosticSettingsFilter, self).__init__(data, manager)
        self.storage_type = data['storage_type']

    schema = type_schema('storage-diagnostic-settings',
                         rinherit=ValueFilter.schema,
                         storage_type={
                             'type': 'string',
                             'enum': [BLOB_TYPE, QUEUE_TYPE, TABLE_TYPE, FILE_TYPE]},
                         required=['storage_type'],
                         )

    def process(self, resources, event=None):
        futures = []
        results = []
        session = local_session(self.manager.session_factory)
        # Process each resource in a separate thread, returning all that pass filter
        with self.executor_factory(max_workers=3) as w:
            for resource_set in chunks(resources, 20):
                futures.append(w.submit(self.process_resource_set, resource_set, session))

            for f in as_completed(futures):
                if f.exception():
                    self.log.warning(
                        "Storage diagnostic settings filter error: %s" % f.exception())
                    continue
                else:
                    results.extend(f.result())

            return results

    def process_resource_set(self, resources, session):
        matched = []
        for resource in resources:
            settings = json.loads(jsonpickle.encode(self.get_settings(resource, session)))
            filtered_settings = super(StorageDiagnosticSettingsFilter, self).process([settings], event=None)

            if filtered_settings:
                matched.append(resource)

        return matched

    def get_settings(self, storage_account, session):
        if self.storage_type == self.BLOB_TYPE:
            return StorageSettingsUtilities.get_blob_settings(storage_account, session)
        elif self.storage_type == self.FILE_TYPE:
            return StorageSettingsUtilities.get_file_settings(storage_account, session)
        elif self.storage_type == self.TABLE_TYPE:
            return StorageSettingsUtilities.get_table_settings(storage_account, session)
        elif self.storage_type == self.QUEUE_TYPE:
            return StorageSettingsUtilities.get_queue_settings(storage_account, session)


class StorageSettingsUtilities(object):

    @staticmethod
    def _get_blob_client_from_storage_account(storage_account, session):
        token = StorageUtilities.get_storage_token(session)

        return BlockBlobService(
            account_name=storage_account['name'],
            token_credential=token
        )

    @staticmethod
    def _get_file_client_from_storage_account(storage_account, session):
        storage_client = session.client('azure.mgmt.storage.StorageManagementClient')

        storage_keys = storage_client.storage_accounts.list_keys(storage_account['resourceGroup'],
                                                                 storage_account['name'])
        primary_key = storage_keys.keys[0].value

        return FileService(
            account_name=storage_account['name'],
            account_key=primary_key
        )

    @staticmethod
    def _get_table_client_from_storage_account(storage_account, session):
        storage_client = session.client('azure.mgmt.storage.StorageManagementClient')

        storage_keys = storage_client.storage_accounts.list_keys(storage_account['resourceGroup'],
                                                                 storage_account['name'])
        primary_key = storage_keys.keys[0].value

        return TableService(
            account_name=storage_account['name'],
            account_key=primary_key
        )

    @staticmethod
    def _get_queue_client_from_storage_account(storage_account, session):
        token = StorageUtilities.get_storage_token(session)
        return QueueService(account_name=storage_account['name'], token_credential=token)

    @staticmethod
    def get_blob_settings(storage_account, session):
        client = StorageSettingsUtilities._get_blob_client_from_storage_account(storage_account, session)
        return client.get_blob_service_properties()

    @staticmethod
    def get_file_settings(storage_account, session):
        file_client = StorageSettingsUtilities._get_file_client_from_storage_account(storage_account, session)
        return file_client.get_file_service_properties()

    @staticmethod
    def get_table_settings(storage_account, session):
        table_client = StorageSettingsUtilities._get_table_client_from_storage_account(storage_account, session)
        return table_client.get_table_service_properties()

    @staticmethod
    def get_queue_settings(storage_account, session):
        queue_client = StorageSettingsUtilities._get_queue_client_from_storage_account(storage_account, session)
        return queue_client.get_queue_service_properties()
