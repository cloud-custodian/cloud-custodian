# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from google.cloud import secretmanager


def gcp_decrypt(config, logger, encrypted_field, client=None):
    if client is None:
        client = secretmanager.SecretManagerServiceClient()
    data = config[encrypted_field]
    if isinstance(data, dict):
        logger.debug(f'Accessing {data["secret"]}')
        if "versions" not in data["secret"]:
            secret = f"{data['secret']}/versions/latest"
        else:
            secret = data["secret"]
        secret_value = client.access_secret_version(name=secret).payload.data.decode("UTF-8")
        return secret_value

    return data
