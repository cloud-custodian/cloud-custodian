# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from google.cloud import secretmanager


CACHE = {}


def gcp_decrypt(config, logger, encrypted_field, client=None):
    global CACHE
    if client is None:
        client = secretmanager.SecretManagerServiceClient()
    data = config[encrypted_field]
    if isinstance(data, dict):
        if "versions" not in data["secret"]:
            secret = f"{data['secret']}/versions/latest"
        else:
            secret = data["secret"]
        if secret in CACHE:
            logger.debug(f"Using cached value for {secret}")
            return CACHE[secret]
        logger.debug(f'Accessing {data["secret"]}')
        secret_value = client.access_secret_version(name=secret).payload.data.decode("UTF-8")
        if secret not in CACHE:
            CACHE[secret] = secret_value
        return secret_value

    return data
