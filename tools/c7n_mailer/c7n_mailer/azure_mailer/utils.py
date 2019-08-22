# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
