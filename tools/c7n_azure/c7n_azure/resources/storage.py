# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import logging

import jsonpickle
from azure.cosmosdb.table import TableService
from azure.mgmt.storage.models import IPRule, \
    NetworkRuleSet, StorageAccountUpdateParameters, VirtualNetworkRule
from azure.storage.blob import BlockBlobService
from azure.storage.common.models import RetentionPolicy, Logging
from azure.storage.file import FileService
from azure.storage.queue import QueueService
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.actions.firewall import SetFirewallAction
from c7n_azure.constants import BLOB_TYPE, FILE_TYPE, QUEUE_TYPE, TABLE_TYPE
from c7n_azure.filters import FirewallRulesFilter, ValueFilter, FirewallBypassFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import ThreadHelper
from netaddr import IPSet

from c7n.exceptions import PolicyValidationError
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
        doc_groups = ['Storage']

        service = 'azure.mgmt.storage'
        client = 'StorageManagementClient'
        enum_spec = ('storage_accounts', 'list', None)
        diagnostic_settings_enabled = False
        resource_type = 'Microsoft.Storage/storageAccounts'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'kind',
            'sku.name'
        )


@Storage.action_registry.register('set-firewall-rules')
class StorageSetFirewallAction(SetFirewallAction):
    """ Set Firewall Rules Action

     Updates Azure Storage Firewalls and Virtual Networks settings.

     By default the firewall rules are appended with the new values.  The ``append: False``
     flag can be used to replace the old rules with the new ones on
     the resource.

     You may also reference azure public cloud Service Tags by name in place of
     an IP address.  Use ``ServiceTags.`` followed by the ``name`` of any group
     from https://www.microsoft.com/en-us/download/details.aspx?id=56519.

     Note that there are firewall rule number limits and that you will likely need to
     use a regional block to fit within the limit.  The limit for storage accounts is
     200 rules.

     .. code-block:: yaml

         - type: set-firewall-rules
               bypass-rules:
                   - Logging
                   - Metrics
               ip-rules:
                   - 11.12.13.0/16
                   - ServiceTags.AppService.CentralUS


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
                 - type: set-firewall-rules
                   append: False
                   bypass-rules:
                       - Logging
                       - Metrics
                   ip-rules:
                       - 11.12.13.0/16
                       - 21.22.23.24
                   virtual-network-rules:
                       - <subnet_resource_id>
                       - <subnet_resource_id>

     """

    schema = type_schema(
        'set-firewall-rules',
        rinherit=SetFirewallAction.schema,
        **{
            'default-action': {'enum': ['Allow', 'Deny'], "default": 'Deny'},
            'bypass-rules': {'type': 'array', 'items': {
                'enum': ['AzureServices', 'Logging', 'Metrics']}},
        }
    )

    log = logging.getLogger('custodian.azure.storage.StorageSetFirewallAction')

    def __init__(self, data, manager=None):
        super(StorageSetFirewallAction, self).__init__(data, manager)
        self.rule_limit = 200

    def _process_resource(self, resource):
        # Build out the ruleset model to update the resource
        rule_set = NetworkRuleSet(default_action=self.data.get('default-action', 'Deny'))

        # Add IP rules
        if self.data.get('ip-rules') is not None:
            existing_ip = [r['value']
                           for r in resource['properties']['networkAcls'].get('ipRules', [])]
            ip_rules = self._build_ip_rules(existing_ip, self.data.get('ip-rules', []))

            # If the user has too many rules raise exception
            if len(ip_rules) > self.rule_limit:
                raise ValueError("Skipped updating firewall for %s. "
                                 "%s exceeds maximum rule count of %s." %
                                 (resource['name'], len(ip_rules), self.rule_limit))

            rule_set.ip_rules = [IPRule(ip_address_or_range=r) for r in ip_rules]

        # Add VNET rules
        if self.data.get('virtual-network-rules') is not None:
            existing_vnet = \
                [r['id'] for r in
                 resource['properties']['networkAcls'].get('virtualNetworkRules', [])]
            vnet_rules = \
                self._build_vnet_rules(existing_vnet, self.data.get('virtual-network-rules', []))
            rule_set.virtual_network_rules = \
                [VirtualNetworkRule(virtual_network_resource_id=r) for r in vnet_rules]

        # Configure BYPASS
        if self.data.get('bypass-rules') is not None:
            existing_bypass = resource['properties']['networkAcls'].get('bypass', '').split(',')
            rule_set.bypass = self._build_bypass_rules(
                existing_bypass, self.data.get('bypass-rules', []))

        # Update resource
        self.client.storage_accounts.update(
            resource['resourceGroup'],
            resource['name'],
            StorageAccountUpdateParameters(network_rule_set=rule_set))


@Storage.filter_registry.register('firewall-rules')
class StorageFirewallRulesFilter(FirewallRulesFilter):

    def _query_rules(self, resource):

        if resource['properties']['networkAcls']['defaultAction'] == 'Deny':
            ip_rules = resource['properties']['networkAcls']['ipRules']
            resource_rules = IPSet([r['value'] for r in ip_rules])
        else:
            resource_rules = IPSet(['0.0.0.0/0'])

        return resource_rules


@Storage.filter_registry.register('firewall-bypass')
class StorageFirewallBypassFilter(FirewallBypassFilter):
    """
    Filters resources by the firewall bypass rules.

    :example:

    This policy will find all Storage Accounts with enabled Azure Services, Metrics and Logging
    bypass rules

    .. code-block:: yaml

        policies:
          - name: storage-bypass
            resource: azure.storage
            filters:
              - type: firewall-bypass
                mode: equal
                list:
                    - AzureServices
                    - Metrics
                    - Logging
    """
    schema = FirewallBypassFilter.schema(['AzureServices', 'Metrics', 'Logging'])

    def _query_bypass(self, resource):
        # Remove spaces from the string for the comparision
        if resource['properties']['networkAcls']['defaultAction'] == 'Allow':
            return ['AzureServices', 'Metrics', 'Logging']

        bypass_string = resource['properties']['networkAcls'].get('bypass', '').replace(' ', '')
        return list(filter(None, bypass_string.split(',')))


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

    :example:

    Find Load Balancers that have logs for both LoadBalancerProbeHealthStatus
    category and LoadBalancerAlertEvent category enabled.
    The use of value_type: swap is important for these examples because it swaps
    the value and the evaluated key so that it evaluates the value provided is in the logs.

    .. code-block:: yaml

        policies:
          - name: find-load-balancers-with-logs-enabled
            resource: azure.loadbalancer
            filters:
              - type: diagnostic-settings
                key: logs[?category == 'LoadBalancerProbeHealthStatus'][].enabled
                value: True
                op: in
                value_type: swap
              - type: diagnostic-settings
                key: logs[?category == 'LoadBalancerAlertEvent'][].enabled
                value: True
                op: in
                value_type: swap

    :example:

    Find KeyVaults that have logs enabled for the AuditEvent category.

    .. code-block:: yaml

        policies:
          - name: find-keyvaults-with-logs-enabled
            resource: azure.keyvault
            filters:
              - type: diagnostic-settings
                key: logs[?category == 'AuditEvent'][].enabled
                value: True
                op: in
                value_type: swap

    """

    schema = type_schema('storage-diagnostic-settings',
                         rinherit=ValueFilter.schema,
                         required=['storage-type'],
                         **{'storage-type': {
                             'type': 'string',
                             'enum': [BLOB_TYPE, QUEUE_TYPE, TABLE_TYPE, FILE_TYPE]}}
                         )

    log = logging.getLogger('custodian.azure.storage.StorageDiagnosticSettingsFilter')

    def __init__(self, data, manager=None):
        super(StorageDiagnosticSettingsFilter, self).__init__(data, manager)
        self.storage_type = data.get('storage-type')

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
        storage_prefix_property = get_annotation_prefix(self.storage_type)

        if not (storage_prefix_property in storage_account):
            settings = StorageSettingsUtilities.get_settings(
                self.storage_type, storage_account, session, token)
            storage_account[storage_prefix_property] = json.loads(jsonpickle.encode(settings))

        return storage_account[storage_prefix_property]


@Storage.action_registry.register('set-log-settings')
class SetLogSettingsAction(AzureBaseAction):
    """Action that updates the logging settings on storage accounts. The action requires
    specifying an array of storage types that will be impacted by the action (blob, queue, table),
    retention (number in days; 0-365), and an array of log settings to enable (read, write, delete).
    The action will disable any settings not listed (e.g. by providing log: [write, delete], the
    action will disable read).

     :example:

        Enable write and delete logging and disable read logging on blob storage,
        and retain logs for 5 days.

     .. code-block:: yaml

        policies:
            - name: enable-blob-storage-logging
              resource: azure.storage
              actions:
                - type: set-log-settings
                  storage-types: [blob]
                  retention: 5
                  log: [write, delete]
    """

    READ = 'read'
    WRITE = 'write'
    DELETE = 'delete'

    schema = type_schema('set-log-settings',
                         required=['storage-types', 'log', 'retention'],
                         **{
                             'storage-types': {
                                 'type': 'array',
                                 'items': {
                                     'type': 'string',
                                     'enum': [BLOB_TYPE, QUEUE_TYPE, TABLE_TYPE]
                                 }
                             },
                             'log': {
                                 'type': 'array',
                                 'items': {
                                     'type': 'string',
                                     'enum': [READ, WRITE, DELETE]
                                 }
                             },
                             'retention': {'type': 'number'}
                         }
                         )
    log = logging.getLogger('custodian.azure.storage.SetLogSettingsAction')

    def __init__(self, data, manager=None):
        super(SetLogSettingsAction, self).__init__(data, manager)
        self.storage_types = data['storage-types']
        self.logs_to_enable = data['log']
        self.retention = data['retention']
        self.token = None

    def validate(self):
        if self.retention < 0 or self.retention > 365:
            raise PolicyValidationError(
                'attribute: retention can not be less than 0 or greater than 365')

    def process_in_parallel(self, resources, event):
        self.token = StorageUtilities.get_storage_token(self.session)
        return super(SetLogSettingsAction, self).process_in_parallel(resources, event)

    def _process_resource(self, resource, event=None):
        retention = RetentionPolicy(enabled=self.retention != 0, days=self.retention)
        log_settings = Logging(self.DELETE in self.logs_to_enable, self.READ in self.logs_to_enable,
                               self.WRITE in self.logs_to_enable, retention_policy=retention)

        for storage_type in self.storage_types:
            StorageSettingsUtilities.update_logging(storage_type, resource,
                                                    log_settings, self.session, self.token)


class StorageSettingsUtilities:

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
    def _get_client(storage_type, storage_account, session=None, token=None):
        if storage_type == TABLE_TYPE or storage_type == FILE_TYPE:
            client = getattr(StorageSettingsUtilities, '_get_{}_client_from_storage_account'
                             .format(storage_type))(storage_account, session)
        else:
            client = getattr(StorageSettingsUtilities, '_get_{}_client_from_storage_account'
                             .format(storage_type))(storage_account, token)

        return client

    @staticmethod
    def get_settings(storage_type, storage_account, session=None, token=None):
        client = StorageSettingsUtilities._get_client(storage_type, storage_account, session, token)

        return getattr(client, 'get_{}_service_properties'.format(storage_type))()

    @staticmethod
    def update_logging(storage_type, storage_account, logging_settings, session=None, token=None):
        client = StorageSettingsUtilities._get_client(storage_type, storage_account, session, token)

        return getattr(client, 'set_{}_service_properties'
                       .format(storage_type))(logging=logging_settings)


@Storage.action_registry.register('require-secure-transfer')
class RequireSecureTransferAction(AzureBaseAction):
    """Action that updates the Secure Transfer setting on Storage Accounts.
    Programmatically, this will be seen by updating the EnableHttpsTrafficOnly setting

    :example:

       Turns on Secure transfer required for all storage accounts. This will reject requests that
       use HTTP to your storage accounts.

    .. code-block:: yaml

        policies:
            - name: require-secure-transfer
              resource: azure.storage
              actions:
              - type: require-secure-transfer
                value: True
    """

    # Default to true assuming user wants secure connection
    schema = type_schema(
        'require-secure-transfer',
        **{
            'value': {'type': 'boolean', "default": True},
        })

    def __init__(self, data, manager=None):
        super(RequireSecureTransferAction, self).__init__(data, manager)

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.storage_accounts.update(
            resource['resourceGroup'],
            resource['name'],
            StorageAccountUpdateParameters(enable_https_traffic_only=self.data.get('value'))
        )
