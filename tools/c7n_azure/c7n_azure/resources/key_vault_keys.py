# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import logging

from azure.keyvault.keys import KeyProperties

from c7n.filters import Filter
from c7n.utils import type_schema

from c7n_azure import constants
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.utils import ThreadHelper, ResourceIdParser


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

        resource = constants.VAULT_AUTH_ENDPOINT
        service = 'azure.keyvault.keys'
        client = 'KeyClient'
        enum_spec = (None, 'list_properties_of_keys', None)

        parent_manager_name = 'keyvault'
        raise_on_exception = False

        id = 'kid'

        default_report_fields = (
            'kid',
            'attributes.enabled',
            'attributes.exp',
            'attributes.recoveryLevel'
        )

        keyvault_child = True

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
        matched = []
        for resource in resources:
            try:
                if 'c7n:kty' not in resource:
                    id = KeyProperties(key_id=resource['id'])
                    client = self.manager.get_client(vault_url=id.vault_url)
                    key = client.get_key(id.name, id.version)

                    resource['c7n:kty'] = key.key.kty.lower()

                if resource['c7n:kty'] in [t.lower() for t in self.data['key-types']]:
                    matched.append(resource)
            except Exception as error:
                log.warning(error)

        return matched


@KeyVaultKeys.filter_registry.register('rotation-policy')
class KeyVaultKeyRotationFilter(Filter):
    """Filters keyvault keys for rotation policy

    :example:

    Find all keyvault key that don't have rotation policy enabled

    .. code-block:: yaml

        policies:
           - name: key-vault-keys-rotation-is-disabled
             resource: azure.keyvault-keys
             filters:
                - type: rotation-policy
                  state: Disabled
    """
    schema = type_schema(
        'rotation-policy', required=['state'],
        state={'type': 'string', 'enum': ['Enabled', 'Disabled']}
    )

    def process(self, resources, event=None):
        matched = []
        for key in resources:
            id = KeyProperties(key_id=key['id'])
            client = self.manager.get_client(vault_url=id.vault_url)
            rotation = client.get_key_rotation_policy(id.name)
            if (self.data.get('state') == 'Disabled' and not rotation.id) or \
               (self.data.get('state') == 'Enabled' and rotation.id):
                matched.append(key)
        return matched


@KeyVaultKeys.action_registry.register("update")
class KeyVaultKeyUpdateAction(AzureBaseAction):
    """
    Update a key's properties. This does not update its cryptographic material.

    expires_on and not_before require isoformatted dates

    :example:

    .. code-block: yaml
        policies:
            - name: update-expires-on
              resource: azure.keyvault-keys
              filters:
                - name: foo
              actions:
                - type: update
                  expires_on: "2025-12-12 00:00:00"
    """

    schema = type_schema(
        "update",
        key_operations={
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "decrypt",
                    "encrypt",
                    "export",
                    "import_key",
                    "sign",
                    "unwrap_key",
                    "verify",
                    "wrap_key"
                ]
            },
        },
        enabled={"type": "boolean"},
        tags={"type": "object"},
        not_before={"type": "string", "format": "date-time"},
        expires_on={"type": "string", "format": "date-time"},
    )

    def _process_resource(self, resource):
        name = resource['vault_id']['resource_id']['name']

        id = KeyProperties(key_id=resource['id'])

        client = self.manager.get_client(vault_url=id.vault_url)

        not_before = self.data.get("not_before")
        expires_on = self.data.get("expires_on")

        if not_before:
            not_before = datetime.datetime.fromisoformat(not_before)

        if expires_on:
            expires_on = datetime.datetime.fromisoformat(expires_on)

        client.update_key_properties(
            name=name,
            key_operations=self.data.get("key_operations"),
            enabled=self.data.get("enabled"),
            tags=self.data.get("tags"),
            not_before=not_before,
            expires_on=expires_on,
        )
