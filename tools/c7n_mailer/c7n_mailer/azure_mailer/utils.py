# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.keyvault.secrets import SecretProperties


def azure_decrypt(config, logger, session, encrypted_field):
    data = config[encrypted_field]  # type: str
    if isinstance(data, dict):
        secret_id = SecretProperties(attributes=None, vault_id=data["secret"])
        kv_client = session.client(
            "azure.keyvault.secrets.SecretClient", vault_url=secret_id.vault_url
        )
        return kv_client.get_secret(secret_id.name, secret_id.version).value

    return data
