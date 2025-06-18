# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from azure.cosmosdb.table import TableService
from azure.mgmt.storage.models import (IPRule, NetworkRuleSet,
                                       StorageAccountUpdateParameters,
                                       VirtualNetworkRule)
from azure.storage.blob import BlobServiceClient
from azure.storage.common.models import Logging, RetentionPolicy
from azure.storage.file import FileService
from azure.storage.queue import QueueServiceClient
from c7n.exceptions import PolicyValidationError
from c7n.filters.core import type_schema, ListItemFilter
from c7n.utils import get_annotation_prefix, local_session
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.actions.firewall import SetFirewallAction
from c7n_azure.constants import BLOB_TYPE, FILE_TYPE, QUEUE_TYPE, TABLE_TYPE
from c7n_azure.filters import (FirewallBypassFilter, FirewallRulesFilter, ValueFilter)
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import ThreadHelper, serialize
from netaddr import IPSet


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


@Storage.filter_registry.register("file-services")
class StorageFileServicesFilter(ListItemFilter):
    """
    Filters Storage Accounts by their file services configuration.

    :example:

    Find storage accounts with file services soft delete disabled

    .. code-block:: yaml

        policies:
          - name: storage-no-file-services-delete-policy
            resource: azure.storage
            filters:
              - type: file-services
                attrs:
                  - type: value
                    key: properties.shareDeleteRetentionPolicy.enabled
                    value: false

    """
    schema = type_schema(
        "file-services",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    item_annotation_key = "c7n:FileServices"
    annotate_items = True

    def _process_resources(self, resources, event=None, client=None):
        if client is None:
            client = self.manager.get_client()

        for res in resources:
            if self.item_annotation_key in res:
                continue
            file_services = client.file_services.list(
                resource_group_name=res["resourceGroup"],
                account_name=res["name"],
            )
            # at least one default is present
            res[self.item_annotation_key] = file_services.serialize(True).get('value', [])

    def process(self, resources, event=None):

        _, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resources,
            executor_factory=self.executor_factory,
            log=self.log,
            client=self.manager.get_client()  # seems like Azure mgmt clients are thread-safe
        )
        if exceptions:
            raise exceptions[0]  # pragma: no cover
        return super().process(resources, event)

    def get_item_values(self, resource):
        return resource.pop(self.item_annotation_key, [])


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


@Storage.filter_registry.register("management-policy-rules")
class StorageAccountManagementPolicyRulesFilter(ListItemFilter):
    """
    Filter Storage Accounts based on their management policy rules

    :example:

    Find storage accounts where lifecycle policy configured to remove base Blob
    after less or equal than 3 days

    .. code-block:: yaml

        policies:
          - name: storage-delete-blob-le-3-days
            resource: azure.storage
            filters:
              - type: management-policy-rules
                attrs:
                  - type: value
                    key: definition.actions.baseBlob.delete.daysAfterModificationGreaterThan
                    value: 3
                    op: le

    """
    schema = type_schema(
        "management-policy-rules",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    item_annotation_key = "c7n:management-policy-rules"
    annotate_items = True

    def get_item_values(self, resource):
        try:
            item = self.manager.get_client().management_policies.get(
                resource_group_name=resource["resourceGroup"],
                account_name=resource["name"],
                management_policy_name="default"
            )
            return item.serialize(True)["properties"]["policy"].get("rules", [])
        except Exception as e:  # azure.core.exceptions.ResourceNotFoundError
            self.log.error(e)
            return []  # no rules


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
        result, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self.process_resource_set,
            executor_factory=self.executor_factory,
            log=self.log,
            session=session
        )
        return result

    def process_resource_set(self, resources, event=None, session=None):
        matched = []
        for resource in resources:
            settings = self._get_settings(resource, session)
            # New SDK renamed the property, this code is to ensure back compat
            if 'analytics_logging' in settings.keys():
                settings['logging'] = settings.pop('analytics_logging')
            filtered_settings = super(StorageDiagnosticSettingsFilter, self).process([settings],
                                                                                     event)

            if filtered_settings:
                matched.append(resource)

        return matched

    def _get_settings(self, storage_account, session=None):
        storage_prefix_property = get_annotation_prefix(self.storage_type)

        if storage_prefix_property not in storage_account:
            settings = StorageSettingsUtilities.get_settings(
                self.storage_type, storage_account, session)
            storage_account[storage_prefix_property] = serialize(settings)

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
        return super(SetLogSettingsAction, self).process_in_parallel(resources, event)

    def _process_resource(self, resource, event=None):

        for storage_type in self.storage_types:
            if storage_type in [BLOB_TYPE, QUEUE_TYPE, FILE_TYPE]:
                log_settings = {
                    'delete': self.DELETE in self.logs_to_enable,
                    'read': self.READ in self.logs_to_enable,
                    'write': self.WRITE in self.logs_to_enable,
                    'retention_policy': {
                        'enabled': self.retention != 0,
                        'days': self.retention if self.retention != 0 else None  # Throws if 0
                    },
                    'version': '1.0'}
            else:
                log_settings = Logging(
                    self.DELETE in self.logs_to_enable,
                    self.READ in self.logs_to_enable,
                    self.WRITE in self.logs_to_enable,
                    retention_policy=RetentionPolicy(
                        enabled=self.retention != 0,
                        days=self.retention))

            StorageSettingsUtilities.update_logging(storage_type, resource,
                                                    log_settings, self.session)


class StorageSettingsUtilities:

    @staticmethod
    def _get_blob_client_from_storage_account(storage_account, session):
        return BlobServiceClient(
            account_url=storage_account['properties']['primaryEndpoints']['blob'],
            credential=session.get_credentials()
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
    def _get_queue_client_from_storage_account(storage_account, session):
        return QueueServiceClient(
            account_url=storage_account['properties']['primaryEndpoints']['queue'],
            credential=session.get_credentials()
        )

    @staticmethod
    def _get_client(storage_type, storage_account, session=None):
        client = getattr(StorageSettingsUtilities, '_get_{}_client_from_storage_account'
                         .format(storage_type))(storage_account, session)
        return client

    @staticmethod
    def get_settings(storage_type, storage_account, session=None):
        client = StorageSettingsUtilities._get_client(storage_type, storage_account, session)

        if storage_type in [QUEUE_TYPE, BLOB_TYPE]:
            return getattr(client, 'get_service_properties')()
        return getattr(client, 'get_{}_service_properties'.format(storage_type))()

    @staticmethod
    def update_logging(storage_type, storage_account, logging_settings, session=None):
        client = StorageSettingsUtilities._get_client(storage_type, storage_account, session)

        if storage_type in [QUEUE_TYPE, BLOB_TYPE]:
            return getattr(client, 'set_service_properties')(analytics_logging=logging_settings)
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

    You can also set the minimum tls version on a bucket,
    valid values: TLS1_0, TLS1_1, TLS1_2:

    .. code-block:: yaml

        policies:
            - name: require-secure-transfer-with-tls-v1-2
              resource: azure.storage
              actions:
              - type: require-secure-transfer
                value: True
                minimum_tls_version: TLS1_2
    """

    # Default to true assuming user wants secure connection
    schema = type_schema(
        'require-secure-transfer',
        minimum_tls_version={"type": "string"},
        **{
            'value': {'type': 'boolean', "default": True},
        })

    def __init__(self, data, manager=None):
        super(RequireSecureTransferAction, self).__init__(data, manager)

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        kwargs = {
            "enable_https_traffic_only": self.data.get("value")
        }

        if self.data.get("minimum_tls_version"):
            kwargs["minimum_tls_version"] = self.data.get("minimum_tls_version")

        update_params = StorageAccountUpdateParameters(**kwargs)
        self.client.storage_accounts.update(
            resource['resourceGroup'],
            resource['name'],
            update_params,
        )


@Storage.filter_registry.register('blob-services')
class BlobServicesFilter(ValueFilter):
    """
    Filter by the current blob services
    configuration for this storage account.

    :example:

    Find storage accounts with blob services soft delete disabled
    or retention less than 7 days

    .. code-block:: yaml

        policies:
          - name: storage-no-soft-delete
            resource: azure.storage
            filters:
              - or:
                  - type: blob-services
                    key: deleteRetentionPolicy.enabled
                    value: false
                  - type: blob-services
                    key: deleteRetentionPolicy.days
                    value: 7
                    op: lt
    """

    schema = type_schema('blob-services', rinherit=ValueFilter.schema)

    log = logging.getLogger('custodian.azure.storage.blob-services-filter')

    def __init__(self, data, manager=None):
        super(BlobServicesFilter, self).__init__(data, manager)

    def process(self, resources, event=None):
        resources, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=self.log
        )
        if exceptions:
            raise exceptions[0]
        return resources

    def _process_resource_set(self, resources, event=None):
        client = self.manager.get_client()
        result = []
        for resource in resources:
            if 'c7n:blobServices' not in resource['properties']:
                blob_services = client.blob_services.get_service_properties(
                    resource['resourceGroup'],
                    resource['name'])

                resource['properties']['c7n:blobServices'] = \
                    blob_services.serialize(True).get('properties', {})

            filtered_resources = super(BlobServicesFilter, self).process(
                [resource['properties']['c7n:blobServices']],
                event)

            if filtered_resources:
                result.append(resource)

        return result
