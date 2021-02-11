# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.constants import RESOURCE_VAULT
from azure.keyvault import KeyVaultId


def azure_decrypt(config, logger, session, encrypted_field):
    data = config[encrypted_field]  # type: str
    if type(data) is dict:
        kv_session = session.get_session_for_resource(resource=RESOURCE_VAULT)
        secret_id = KeyVaultId.parse_secret_id(data['secret'])
        kv_client = kv_session.client('azure.keyvault.KeyVaultClient')
        return kv_client.get_secret(secret_id.vault, secret_id.name, secret_id.version).value

    return data
