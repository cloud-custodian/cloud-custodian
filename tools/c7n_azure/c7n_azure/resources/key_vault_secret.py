# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n_azure import constants
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo

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
