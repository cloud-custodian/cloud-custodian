# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

try:
    from google.cloud import secretmanager
except ImportError:
    print("GCP secret manager SDK required to decrypt secured string: "
          "pip install google-cloud-secret-manager")


def gcp_decrypt(config, logger, encrypted_field,
                client=secretmanager.SecretManagerServiceClient()):
    data = config[encrypted_field]
    if type(data) is dict:
        logger.debug(f'Accessing {data["secret"]}')
        if "versions" not in data['secret']:
            secret = f"{data['secret']}/versions/latest"
        else:
            secret = data['secret']
        secret_value = client.access_secret_version(name=secret)
        return secret_value.payload.data.decode("UTF-8")

    return data
