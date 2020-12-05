# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from azure.keyvault.key_vault_id import KeyVaultId

from c7n.filters import Filter
from c7n.utils import type_schema

from c7n_azure import constants
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.utils import ThreadHelper, ResourceIdParser, generate_key_vault_url


log = logging.getLogger('custodian.azure.keyvault.keys')


@resources.register('keyvault-key', aliases=['keyvault-keys'])
class KeyVaultKeys(ChildResourceManager):
    """Key Vault Key Resource

    :example:

    This policy will find all Keys in `keyvault_test` and `keyvault_prod` KeyVaults

    .. code-block:: yaml

        policies:
          - name: keyvault-keys
            description:
              List all keys from 'keyvault_test' and 'keyvault_prod' vaults
            resource: azure.keyvault-key
            filters:
              - type: keyvault
                vaults:
                  - keyvault_test
                  - keyvault_prod

    :example:

    This policy will find all Keys in all KeyVaults that are older than 30 days

    .. code-block:: yaml

        policies:
          - name: keyvault-keys
            description:
              List all keys that are older than 30 days
            resource: azure.keyvault-key
            filters:
              - type: value
                key: attributes.created
                value_type: age
                op: gt
                value: 30

    :example:

    If your company wants to enforce usage of HSM-backed keys in the KeyVaults,
    you can use this policy to find all Keys in all KeyVaults not backed by an HSM module.

    .. code-block:: yaml

        policies:
          - name: keyvault-keys
            description:
              List all non-HSM keys
            resource: azure.keyvault-key
            filters:
              - not:
                 - type: key-type
                   key-types:
                     - RSA-HSM, EC-HSM

    """

    class resource_type(ChildTypeInfo):
        doc_groups = ['Security']

        resource = constants.RESOURCE_VAULT
        service = 'azure.keyvault'
        client = 'KeyVaultClient'
        enum_spec = (None, 'get_keys', None)

        parent_manager_name = 'keyvault'
        raise_on_exception = False

        id = 'kid'

        default_report_fields = (
            'kid',
            'attributes.enabled',
            'attributes.exp',
            'attributes.recoveryLevel'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {'vault_base_url': generate_key_vault_url(parent_resource['name'])}

    def augment(self, resources):
        resources = super(KeyVaultKeys, self).augment(resources)
        # When KeyVault contains certificates, it creates corresponding key and secret objects to
        # store cert data. They are managed by KeyVault it is not possible to do any actions.
        return [r for r in resources if not r.get('managed')]


@KeyVaultKeys.filter_registry.register('keyvault')
class KeyVaultFilter(Filter):
    schema = type_schema(
        'keyvault',
        required=['vaults'],
        **{
            'vaults': {'type': 'array', 'items': {'type': 'string'}}
        }
    )

    def process(self, resources, event=None):
        parent_key = self.manager.resource_type.parent_key
        return [r for r in resources
                if ResourceIdParser.get_resource_name(r[parent_key]) in self.data['vaults']]


@KeyVaultKeys.filter_registry.register('key-type')
class KeyTypeFilter(Filter):
    schema = type_schema(
        'key-type',
        **{
            'key-types': {'type': 'array', 'items': {'enum': ['EC', 'EC-HSM', 'RSA', 'RSA-HSM']}}
        }
    )

    def process(self, resources, event=None):

        resources, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log
        )
        return resources

    def _process_resource_set(self, resources, event):
        client = self.manager.get_client()

        matched = []
        for resource in resources:
            try:
                if 'c7n:kty' not in resource:
                    id = KeyVaultId.parse_key_id(resource['kid'])
                    key = client.get_key(id.vault, id.name, id.version)

                    resource['c7n:kty'] = key.key.kty.lower()

                if resource['c7n:kty'] in [t.lower() for t in self.data['key-types']]:
                    matched.append(resource)
            except Exception as error:
                log.warning(error)

        return matched
