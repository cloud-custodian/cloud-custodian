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

import json
import logging

import jsonpickle
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
from c7n_azure.utils import ThreadHelper
from netaddr import IPNetwork

from c7n.filters.core import type_schema
from c7n.utils import local_session, get_annotation_prefix


@resources.register('storage')
class Storage(ArmResourceManager):
    """Storage Account Resource

    :example:

    Finds all Storage Accounts in the subscription.

    .. code-block:: yaml

        policies:
            - name: find-all-storage-accounts
              resource: azure.storage

    """

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.storage'
        client = 'StorageManagementClient'
        enum_spec = ('storage_accounts', 'list', None)
        diagnostic_settings_enabled = False
        resource_type = 'Microsoft.Storage/storageAccounts'


@Storage.action_registry.register('set-network-rules')
class StorageSetNetworkRulesAction(AzureBaseAction):
    """ Set Network Rules Action

    Updates Azure Storage Firewalls and Virtual Networks settings.

    :example:

    Find storage accounts without any firewall rules.

    Configure default-action to ``Deny`` and then allow:
    - Azure Logging and Metrics services
    - Two specific IPs
    - Two subnets

    .. code-block:: yaml

        policies:
            - name: add-storage-firewall
              resource: azure.storage

            filters:
                - type: value
                  key: properties.networkAcls.ipRules
                  value_type: size
                  op: eq
                  value: 0

            actions:
                - type: set-network-rules
                  default-action: Deny
                  bypass: [Logging, Metrics]
                  ip-rules:
                      - ip-address-or-range: 11.12.13.14
                      - ip-address-or-range: 21.22.23.24
                  virtual-network-rules:
                      - virtual-network-resource-id: <subnet_resource_id>
                      - virtual-network-resource-id: <subnet_resource_id>

    """

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
    """Filters storage accounts based on its diagnostic settings. The filter requires
    specifying the storage type (blob, queue, table, file) and will filter based on
    the settings for that specific type.

     :example:

        Find all storage accounts that have a 'delete' logging setting disabled.

     .. code-block:: yaml

        policies:
            - name: find-accounts-with-delete-logging-disabled
              resource: azure.storage
              filters:
                - or:
                    - type: storage-diagnostic-settings
                      storage-type: blob
                      key: logging.delete
                      op: eq
                      value: False
                    - type: storage-diagnostic-settings
                      storage-type: queue
                      key: logging.delete
                      op: eq
                      value: False
                    - type: storage-diagnostic-settings
                      storage-type: table
                      key: logging.delete
                      op: eq
                      value: False
    """

    BLOB_TYPE = 'blob'
    QUEUE_TYPE = 'queue'
    TABLE_TYPE = 'table'
    FILE_TYPE = 'file'

    schema = type_schema('storage-diagnostic-settings',
                         rinherit=ValueFilter.schema,
                         required=['storage-type'],
                         **{'storage-type': {
                             'type': 'string',
                             'enum': [BLOB_TYPE, QUEUE_TYPE, TABLE_TYPE, FILE_TYPE]}}
                         )

    def __init__(self, data, manager=None):
        super(StorageDiagnosticSettingsFilter, self).__init__(data, manager)
        self.storage_type = data.get('storage-type')
        self.log = logging.getLogger('custodian.azure.storage')

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        token = StorageUtilities.get_storage_token(session)
        result, errors = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self.process_resource_set,
            executor_factory=self.executor_factory,
            log=self.log,
            session=session,
            token=token
        )
        return result

    def process_resource_set(self, resources, event=None, session=None, token=None):
        matched = []
        for resource in resources:
            settings = self._get_settings(resource, session, token)
            filtered_settings = super(StorageDiagnosticSettingsFilter, self).process([settings],
                                                                                     event)

            if filtered_settings:
                matched.append(resource)

        return matched

    def _get_settings(self, storage_account, session=None, token=None):
        if self.storage_type == self.BLOB_TYPE:
            blob_property = get_annotation_prefix(self.BLOB_TYPE)
            if not (blob_property in storage_account):
                storage_account[blob_property] = json.loads(jsonpickle.encode(
                    StorageSettingsUtilities.get_blob_settings(storage_account, token)))
            return storage_account[blob_property]

        elif self.storage_type == self.FILE_TYPE:
            file_property = get_annotation_prefix(self.FILE_TYPE)
            if not (file_property in storage_account):
                storage_account[file_property] = json.loads(jsonpickle.encode(
                    StorageSettingsUtilities.get_file_settings(storage_account, session)))
            return storage_account[file_property]

        elif self.storage_type == self.TABLE_TYPE:
            table_property = get_annotation_prefix(self.TABLE_TYPE)
            if not (table_property in storage_account):
                storage_account[table_property] = json.loads(jsonpickle.encode(
                    StorageSettingsUtilities.get_table_settings(storage_account, session)))
            return storage_account[table_property]

        elif self.storage_type == self.QUEUE_TYPE:
            queue_property = get_annotation_prefix(self.QUEUE_TYPE)
            if not (queue_property in storage_account):
                storage_account[queue_property] = json.loads(jsonpickle.encode(
                    StorageSettingsUtilities.get_queue_settings(storage_account, token)))
            return storage_account[queue_property]


class StorageSettingsUtilities(object):

    @staticmethod
    def _get_blob_client_from_storage_account(storage_account, token):
        return BlockBlobService(
            account_name=storage_account['name'],
            token_credential=token
        )

    @staticmethod
    def _get_file_client_from_storage_account(storage_account, session):
        primary_key = StorageUtilities.get_storage_primary_key(storage_account['resourceGroup'],
                                                               storage_account['name'],
                                                               session)

        return FileService(
            account_name=storage_account['name'],
            account_key=primary_key
        )

    @staticmethod
    def _get_table_client_from_storage_account(storage_account, session):
        primary_key = StorageUtilities.get_storage_primary_key(storage_account['resourceGroup'],
                                                               storage_account['name'],
                                                               session)

        return TableService(
            account_name=storage_account['name'],
            account_key=primary_key
        )

    @staticmethod
    def _get_queue_client_from_storage_account(storage_account, token):
        return QueueService(account_name=storage_account['name'], token_credential=token)

    @staticmethod
    def get_blob_settings(storage_account, session):
        client = StorageSettingsUtilities._get_blob_client_from_storage_account(
            storage_account, session)
        return client.get_blob_service_properties()

    @staticmethod
    def get_file_settings(storage_account, session):
        file_client = StorageSettingsUtilities._get_file_client_from_storage_account(
            storage_account, session)
        return file_client.get_file_service_properties()

    @staticmethod
    def get_table_settings(storage_account, session):
        table_client = StorageSettingsUtilities._get_table_client_from_storage_account(
            storage_account, session)
        return table_client.get_table_service_properties()

    @staticmethod
    def get_queue_settings(storage_account, session):
        queue_client = StorageSettingsUtilities._get_queue_client_from_storage_account(
            storage_account, session)
        return queue_client.get_queue_service_properties()
