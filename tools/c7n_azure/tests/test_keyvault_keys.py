# Copyright 2015-2018 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest, arm_template
from c7n_azure.session import Session
from c7n.utils import local_session, reset_session_cache


class KeyVaultKeyTest(BaseTest):

    def test_key_vault_keys_schema_validate(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-keys',
            'filters': [
                {'type': 'keyvault', 'vaults': ['kv1', 'kv2']},
                {'type': 'key-type', 'key-types': ['RSA', 'RSA-HSM', 'EC', 'EC-HSM']}
            ]
        }, validate=True)
        self.assertTrue(p)

    @arm_template('keyvault.json')
    def test_key_vault_keys_keyvault(self):
        mgmt_client = local_session(Session).client('azure.mgmt.keyvault.KeyVaultManagementClient')
        kvs = [k for k in mgmt_client.vaults.list_by_resource_group('test_keyvault')]
        self.assertEqual(len(kvs), 1)
        reset_session_cache()

        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-keys',
            'filters': [
                {
                    'type': 'keyvault',
                    'vaults': [kvs[0].name]
                },
            ]
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    @arm_template('keyvault.json')
    def test_key_vault_keys_type(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-keys',
            'filters': [
                {
                    'type': 'key-type',
                    'key-types': ['RSA', 'RSA-HSM']
                },
            ]
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['c7n:kty'].lower(), 'rsa')
