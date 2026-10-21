# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n.utils import type_schema

from c7n_azure import constants
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.resources.key_vault import KeyVaultPropertiesUpdateAction

log = logging.getLogger('custodian.azure.keyvault.secrets')


@resources.register('keyvault-secret')
class KeyVaultSecret(ChildResourceManager):
    """Key Vault Secret Resource

    :example:

    This policy will find all secrets that don't have expiration date set

    .. code-block:: yaml

        policies:
          - name: keyvault-secrets
            description:
              List all secrets that don't have expiration date set
            resource: azure.keyvault-secret
            filters:
              - type: value
                key: attributes.expires
                value: null

    """

    class resource_type(ChildTypeInfo):
        doc_groups = ['Security']

        resource = constants.VAULT_AUTH_ENDPOINT
        service = 'azure.keyvault.secrets'
        client = 'SecretClient'
        enum_spec = (None, 'list_properties_of_secrets', None)

        parent_manager_name = 'keyvault'
        raise_on_exception = False

        default_report_fields = (
            'id',
            'attributes.expires'
        )

        keyvault_child = True

    def enumerate_resources(self, *args, **kw):
        # azure keyvaults secrets from version 4.9 to 4.10 made incompatible output
        # changes to move attributes to a subdictionary ('data'), this would break
        # extant policies, so preserve compatiblity.
        resources = super().enumerate_resources(*args, **kw)
        for r in resources:
            data = r['attributes'].pop('data', {})
            # also incompatible change of expires to exp :/
            if 'exp' in data:
                data['expires'] = data['exp']
            r['attributes'].update(data)
        return resources


@KeyVaultSecret.action_registry.register('update')
class KeyVaultSecretUpdateAction(KeyVaultPropertiesUpdateAction):
    """
    Update a secret's properties. This does not change the secret's value.

    ``expires_on`` and ``not_before`` require ISO formatted dates.
    ``expires_in_days`` sets the expiration date relative to the time
    the policy runs, and cannot be combined with ``expires_on``.
    ``tags`` are merged into the secret's existing tags.

    :example:

    Set an expiration date one year out on all secrets without one

    .. code-block:: yaml

        policies:
          - name: keyvault-secret-set-expiration
            resource: azure.keyvault-secret
            filters:
              - type: value
                key: attributes.expires
                value: null
            actions:
              - type: update
                expires_in_days: 365
    """

    schema = type_schema(
        'update',
        enabled={'type': 'boolean'},
        tags={'type': 'object'},
        content_type={'type': 'string'},
        not_before={'type': 'string', 'format': 'date-time'},
        expires_on={'type': 'string', 'format': 'date-time'},
        expires_in_days={'type': 'integer', 'minimum': 1},
    )

    def _process_resource(self, resource):
        resource_id = resource['vault_id']['resource_id']
        client = self.manager.get_client(vault_url=resource_id['vault_url'])

        # Key Vault replaces the whole tag set, so merge into the existing tags.
        tags = self.data.get('tags')
        if tags is not None:
            tags = {**(resource.get('tags') or {}), **tags}

        client.update_secret_properties(
            name=resource_id['name'],
            enabled=self.data.get('enabled'),
            tags=tags,
            content_type=self.data.get('content_type'),
            not_before=self.not_before,
            expires_on=self.expires_on,
        )
