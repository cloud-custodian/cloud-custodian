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

from azure_common import BaseTest, arm_template, DEFAULT_TENANT_ID
from c7n_azure.resources.key_vault import WhiteListFilter
from mock import patch
from msrestazure.azure_exceptions import CloudError


class KeyVaultTest(BaseTest):
    def setUp(self):
        super(KeyVaultTest, self).setUp()

    def test_key_vault_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-key-vault',
                'resource': 'azure.keyvault',
                'filters': [
                    {'type': 'whitelist',
                     'key': 'test'}
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('keyvault.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault1*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_compare_permissions(self):
        p1 = {"keys": ['get'], "secrets": ['get'], "certificates": ['get']}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertTrue(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {"keys": ['delete']}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertFalse(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {"secrets": ['delete']}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertFalse(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {"certificates": ['delete']}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertFalse(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {}
        p2 = {"keys": ['Get', 'List'], "secrets": ['Get', 'List'], "certificates": ['Get', 'List']}
        self.assertTrue(WhiteListFilter.compare_permissions(p1, p2))

        p1 = {"keys": ['get'], "secrets": ['get'], "certificates": ['get']}
        p2 = {}
        self.assertFalse(WhiteListFilter.compare_permissions(p1, p2))

    @arm_template('keyvault.json')
    @patch('c7n_azure.session.Session.get_tenant_id', return_value=DEFAULT_TENANT_ID)
    def test_whitelist(self, get_tenant_id):
        """Tests basic whitelist functionality"""
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault1*'},
                {'not': [
                    {'type': 'whitelist',
                     'key': 'principalName',
                     'users': ['account1@sample.com']}
                ]}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault-no-policies.json')
    def test_whitelist_zero_access_policies(self):
        """Tests that a keyvault with 0 access policies is processed properly
        and doesn't raise an exception.
        """
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault2*'},
                {'not': [
                    {'type': 'whitelist',
                     'key': 'principalName',
                     'users': ['account1@sample.com']}
                ]}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('keyvault.json')
    @patch('c7n_azure.session.Session.get_tenant_id', return_value=DEFAULT_TENANT_ID)
    def test_whitelist_not_authorized(self, get_tenant_id):
        """Tests that an exception is thrown when both:
        * The Microsoft Graph call fails
        * A Graph provided field is being measured (principleName in this case)
        Note: to regenerate the cassette for this test case, use a service principle / user who
        does not have the correct permissions to access Microsoft Graph:
        See https://docs.microsoft.com/en-us/graph/api/directoryobject-getbyids for required
        permissions.
        """
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault1*'},
                {'not': [
                    {'type': 'whitelist',
                     'key': 'principalName',
                     'users': ['account1@sample.com']}
                ]}
            ]
        })

        with self.assertRaises(CloudError) as e:
            p.run()

        self.assertEqual(403, e.exception.status_code)
        self.assertEqual("Operation failed with status: 'Forbidden'. Details: 403 Client Error: "
                         "Forbidden for url: https://graph.windows.net/"
                         "ea42f556-5106-4743-99b0-c129bfa71a47/getObjectsByObjectIds?"
                         "api-version=1.6", e.exception.message)
