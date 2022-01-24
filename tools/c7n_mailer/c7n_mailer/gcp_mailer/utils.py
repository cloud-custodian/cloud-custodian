# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

# pip3 install --user google-cloud-secret-manager  # TODO:
from google.cloud import secretmanager


def gcp_decrypt(config, encrypted_field, logger=None, client=secretmanager.SecretManagerServiceClient()):
    data = config[encrypted_field]
    if type(data) is dict:
        secret_value = client.access_secret_version(name = data['secret'])
        return secret_value.payload.data.decode("UTF-8")

    return data
