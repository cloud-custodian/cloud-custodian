# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from azure.keyvault.key_vault_id import StorageAccountId
from c7n_azure import constants
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.utils import generate_key_vault_url

from c7n.filters import ValueFilter
from c7n.utils import get_annotation_prefix as gap
from c7n.utils import type_schema

log = logging.getLogger('custodian.azure.keyvault.storage')


@resources.register('keyvault-storage')
class KeyVaultStorage(ChildResourceManager):
    """Key Vault Managed Storage Account Resource

    :example:

    List all Key Vault managed Storage Accounts

    .. code-block:: yaml

        policies:
          - name: keyvault-storage
            resource: azure.keyvault-storage

    """

    class resource_type(ChildTypeInfo):
        doc_groups = ['Security']

        resource = constants.RESOURCE_VAULT
        service = 'azure.keyvault'
        client = 'KeyVaultClient'
        enum_spec = (None, 'get_storage_accounts', None)

        parent_manager_name = 'keyvault'
        raise_on_exception = False

        @classmethod
        def extra_args(cls, parent_resource):
            return {'vault_base_url': generate_key_vault_url(parent_resource['name'])}

    # get_storage_accounts method returns very limited amount of information. For any meaningful
    # filter or action we have to query some extra data, so augment is the best possible place.
    def augment(self, resources):
        resources = super(KeyVaultStorage, self).augment(resources)

        client = self.get_client()
        extra_fields = ['autoRegenerateKey', 'regenerationPeriod', 'activeKeyName']

        for r in resources:
            sid = StorageAccountId(r['id'])
            data = client.get_storage_account(sid.vault, sid.name).serialize(True)
            r[gap('extra')] = {k: v for k, v in data.items() if k in extra_fields}

        return resources


@KeyVaultStorage.filter_registry.register('auto-regenerate-key')
class KeyVaultStorageAutoRegenerateKeyFilter(ValueFilter):
    """Filter Key Vault Managed Storage Account Resource on Auto Regenerate property.

    This is ``Value`` based filter, you can provide boolean ``value`` property.

    :example:

    List all Key Vault managed Storage Accounts with disabled automatic keys regeneration

    .. code-block:: yaml

        policies:
          - name: keyvault-storage-auto-regenerate
            resource: azure.keyvault-storage
            filters:
              - type: auto-regenerate-key
                value: False

    """
    schema = type_schema(
        'auto-regenerate-key',
        rinherit=ValueFilter.schema,
        **{
            'key': None,
            'op': None,
            'value_type': None,
            'value': {'type': 'boolean'}
        }
    )

    def __init__(self, *args, **kwargs):
        super(KeyVaultStorageAutoRegenerateKeyFilter, self).__init__(*args, **kwargs)
        self.data['key'] = '"{0}".autoRegenerateKey'.format(gap('extra'))
        self.data['op'] = 'eq'


@KeyVaultStorage.filter_registry.register('regeneration-period')
class KeyVaultStorageRegenerationPeriodFilter(ValueFilter):
    """Filter Key Vault Managed Storage Account Resource on Regeneration Period property.

    This is ``Value`` based filter, you can provide any ``value`` and ``op`` properties.

    :example:

    List all Key Vault managed Storage Accounts with regeneration period not equal to P90D

    .. code-block:: yaml


        policies:
          - name: keyvault-storage-regeneration-period
            resource: azure.keyvault-storage
            filters:
              - type: regeneration-period
                op: ne
                value: P90D

    """
    schema = type_schema(
        'regeneration-period',
        rinherit=ValueFilter.schema,
        **{
            'key': None,
            'value_type': None
        }
    )

    def __init__(self, *args, **kwargs):
        super(KeyVaultStorageRegenerationPeriodFilter, self).__init__(*args, **kwargs)
        self.data['key'] = '"{0}".regenerationPeriod'.format(gap('extra'))


@KeyVaultStorage.filter_registry.register('active-key-name')
class KeyVaultStorageActiveKeyNameFilter(ValueFilter):
    """Filter Key Vault Managed Storage Account Resource on Active Key Name property.

    This is ``Value`` based filter, you can provide string ``value`` property.

    ``value_type`` is always ``normalize``.

    :example:

    List all Key Vault managed Storage Accounts with Active Key Name key1

    .. code-block:: yaml

        policies:
          - name: keyvault-storage-active-key-name
            resource: azure.keyvault-storage
            filters:
              - type: active-key-name
                value: key1

    """
    schema = type_schema(
        'active-key-name',
        rinherit=ValueFilter.schema,
        required=['value'],
        **{
            'key': None,
            'op': None,
            'value_type': None,
            'value': {'type': 'string'}
        }
    )

    def __init__(self, *args, **kwargs):
        super(KeyVaultStorageActiveKeyNameFilter, self).__init__(*args, **kwargs)
        self.data['key'] = '"{0}".activeKeyName'.format(gap('extra'))
        self.data['op'] = 'eq'
        self.data['value_type'] = 'normalize'


@KeyVaultStorage.action_registry.register('regenerate-key')
class KeyVaultStorageRegenerateKeyAction(AzureBaseAction):
    """
    Regenerate Managed Storage Access Key

    :example:

    Regenerate all Access Keys older than 30 days.

    .. code-block:: yaml

        policies:
          - name: azure-managed-storage-regenerate-key
            resource: azure.keyvault-storage
            filters:
              - type: value
                key: attributes.updated
                op: gt
                value_type: age
                value: 30
            actions:
             - type: regenerate-key

    """

    schema = type_schema('regenerate-key')

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        sid = StorageAccountId(resource['id'])
        self.client.regenerate_storage_account_key(sid.vault,
                                                   sid.name,
                                                   resource[gap('extra')]['activeKeyName'])


@KeyVaultStorage.action_registry.register('update')
class KeyVaultStorageUpdateAction(AzureBaseAction):
    """
    Update Key Vault Managed Storage Account properties.

    :example:

    Ensure all keys have auto regenerate enabled with 30 days rotation policy.

    .. code-block:: yaml

        policies:
          - name: azure-managed-storage-update
            resource: azure.keyvault-storage
            filters:
              - or:
                - type: auto-regenerate-key
                  value: false
                - type: regeneration-period
                  op: ne
                  value: P30D
            actions:
             - type: update
               auto-regenerate-key: true
               regeneration-period: P30D

    """

    schema = type_schema(
        'update',
        **{
            'active-key-name': {'type': 'string'},
            'auto-regenerate-key': {'type': 'boolean'},
            'regeneration-period': {'type': 'string'},
        })

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        sid = StorageAccountId(resource['id'])
        self.client.update_storage_account(
            sid.vault,
            sid.name,
            active_key_name=self.data.get('active-key-name', None),
            auto_regenerate_key=self.data.get('auto-regenerate-key', None),
            regeneration_period=self.data.get('regeneration-period', None))
