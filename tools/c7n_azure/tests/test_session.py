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

try:
    from importlib import reload
except Exception:
    pass  # Python 2.7 has reload built-in

import json
import os
import re
import sys

from azure.common.credentials import ServicePrincipalCredentials, BasicTokenAuthentication
from msrestazure.azure_active_directory import MSIAuthentication
from azure_common import BaseTest, DEFAULT_SUBSCRIPTION_ID, DEFAULT_TENANT_ID
from c7n_azure import constants
from c7n_azure.session import Session
from mock import patch

CUSTOM_SUBSCRIPTION_ID = '00000000-5106-4743-99b0-c129bfa71a47'


class SessionTest(BaseTest):

    authorization_file = os.path.join(os.path.dirname(__file__), 'data', 'test_auth_file.json')
    authorization_file_kv = os.path.join(os.path.dirname(__file__), 'data',
                                         'test_auth_file_kv.json')
    authorization_file_full = os.path.join(os.path.dirname(__file__),
                                           'data',
                                           'test_auth_file_full.json')

    def setUp(self):
        super(SessionTest, self).setUp()

    def tearDown(self):
        super(SessionTest, self).tearDown()
        reload(sys.modules['c7n_azure.session'])

    def mock_init(self, client_id, secret, tenant, resource):
        pass

    def test_initialize_session_auth_file(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__',
                   autospec=True, return_value=None):
            s = Session(authorization_file=self.authorization_file)

            self.assertIs(type(s.get_credentials()), ServicePrincipalCredentials)
            self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)
            self.assertEqual(s.get_tenant_id(), 'tenant')

    def test_initialize_session_auth_file_custom_subscription(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__',
                   autospec=True, return_value=None):
            s = Session(subscription_id=CUSTOM_SUBSCRIPTION_ID,
                        authorization_file=self.authorization_file)

            self.assertIs(type(s.get_credentials()), ServicePrincipalCredentials)
            self.assertEqual(s.get_subscription_id(), CUSTOM_SUBSCRIPTION_ID)

            # will vary between recorded/live auth options but useful to ensure
            # we ended up with one of the valid values
            self.assertTrue(s.get_tenant_id() in [DEFAULT_TENANT_ID, 'tenant'])

    def test_initialize_session_principal(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__',
                   autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                constants.ENV_TENANT_ID: DEFAULT_TENANT_ID,
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                                constants.ENV_CLIENT_ID: 'client',
                                constants.ENV_CLIENT_SECRET: 'secret'
                            }, clear=True):

                s = Session()

                self.assertIs(type(s.get_credentials()), ServicePrincipalCredentials)
                self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)
                self.assertEqual(s.get_tenant_id(), DEFAULT_TENANT_ID)

    def test_initialize_msi_auth_system(self):
        with patch('msrestazure.azure_active_directory.MSIAuthentication.__init__',
                   autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                constants.ENV_USE_MSI: 'true',
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID
                            }, clear=True):
                s = Session()

                self.assertIs(type(s.get_credentials()), MSIAuthentication)
                self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)

    def test_initialize_msi_auth_user(self):
        with patch('msrestazure.azure_active_directory.MSIAuthentication.__init__',
                   autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                constants.ENV_USE_MSI: 'true',
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                                constants.ENV_CLIENT_ID: 'client'
                            }, clear=True):
                s = Session()

                self.assertIs(type(s.get_credentials()), MSIAuthentication)
                self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)

    def test_initialize_session_token(self):
        with patch.dict(os.environ,
                        {
                            constants.ENV_ACCESS_TOKEN: 'token',
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID
                        }, clear=True):

            s = Session()

            self.assertIs(type(s.get_credentials()), BasicTokenAuthentication)
            self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)

    def test_get_functions_auth_string(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__',
                   autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                constants.ENV_TENANT_ID: 'tenant',
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                                constants.ENV_CLIENT_ID: 'client',
                                constants.ENV_CLIENT_SECRET: 'secret'
                            }, clear=True):
                s = Session()

                auth = s.get_functions_auth_string(CUSTOM_SUBSCRIPTION_ID)

                expected = {"client_id": "client",
                            "client_secret": "secret",
                            "tenant_id": "tenant",
                            "subscription_id": CUSTOM_SUBSCRIPTION_ID}

                self.assertEqual(json.loads(auth), expected)

    def test_get_functions_auth_string_overrides(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__',
                   autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                constants.ENV_TENANT_ID: 'tenant',
                                constants.ENV_SUB_ID: 'ea42f556-5106-4743-99b0-c129bfa71a47',
                                constants.ENV_CLIENT_ID: 'client',
                                constants.ENV_CLIENT_SECRET: 'secret',
                                constants.ENV_FUNCTION_TENANT_ID: 'functiontenant',
                                constants.ENV_FUNCTION_SUB_ID: '000000-5106-4743-99b0-c129bfa71a47',
                                constants.ENV_FUNCTION_CLIENT_ID: 'functionclient',
                                constants.ENV_FUNCTION_CLIENT_SECRET: 'functionsecret'
                            }, clear=True):
                s = Session()

                auth = s.get_functions_auth_string('000000-5106-4743-99b0-c129bfa71a47')

                expected = """{"client_id": "functionclient",
                               "client_secret": "functionsecret",
                               "tenant_id": "functiontenant",
                               "subscription_id": "000000-5106-4743-99b0-c129bfa71a47"
                             }"""

                self.assertEqual(json.loads(auth), json.loads(expected))

    def test_get_function_target_subscription(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__',
                   autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                constants.ENV_TENANT_ID: 'tenant',
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                                constants.ENV_CLIENT_ID: 'client',
                                constants.ENV_CLIENT_SECRET: 'secret'
                            }, clear=True):
                s = Session()
                self.assertEqual(s.get_function_target_subscription_name(),
                                 DEFAULT_SUBSCRIPTION_ID)
                self.assertEqual(s.get_function_target_subscription_ids(),
                                 [DEFAULT_SUBSCRIPTION_ID])

            with patch.dict(os.environ,
                            {
                                constants.ENV_TENANT_ID: 'tenant',
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                                constants.ENV_CLIENT_ID: 'client',
                                constants.ENV_CLIENT_SECRET: 'secret',
                                constants.ENV_FUNCTION_SUB_ID: CUSTOM_SUBSCRIPTION_ID
                            }, clear=True):
                s = Session()
                self.assertEqual(s.get_function_target_subscription_name(),
                                 CUSTOM_SUBSCRIPTION_ID)
                self.assertEqual(s.get_function_target_subscription_ids(),
                                 [CUSTOM_SUBSCRIPTION_ID])

            with patch.dict(os.environ,
                            {
                                constants.ENV_TENANT_ID: 'tenant',
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                                constants.ENV_CLIENT_ID: 'client',
                                constants.ENV_CLIENT_SECRET: 'secret',
                                constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME: 'test'
                            }, clear=True):
                with patch('c7n_azure.utils.ManagedGroupHelper.get_subscriptions_list',
                           return_value=[]):
                    s = Session()
                    self.assertEqual(s.get_function_target_subscription_name(), 'test')
                    self.assertEqual(s.get_function_target_subscription_ids(), [])

    def test_api_version(self):
        """Verify we retrieve the correct API version for a resource type"""
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        resource = next(client.resources.list())
        self.assertTrue(re.match('\\d{4}-\\d{2}-\\d{2}',
                                 s.resource_api_version(resource.id)) is not None)

    def test_get_session_for_resource(self):
        s = Session()
        resource_session = s.get_session_for_resource(constants.RESOURCE_STORAGE)
        self.assertEqual(resource_session.resource_namespace, constants.RESOURCE_STORAGE)

    @patch('c7n_azure.utils.custodian_azure_send_override')
    def test_get_client_overrides(self, mock):
        # Reload the module to re-import patched function
        reload(sys.modules['c7n_azure.session'])
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        self.assertFalse(client._client.config.retry_policy.policy.respect_retry_after_header)
        self.assertIsNotNone(client._client.orig_send)
        client._client.send()
        self.assertTrue(mock.called)

    @patch('c7n_azure.utils.get_keyvault_secret', return_value='{}')
    def test_compare_auth_params(self, _1):
        reload(sys.modules['c7n_azure.session'])
        with patch.dict(os.environ,
                        {
                            constants.ENV_TENANT_ID: 'tenant',
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                            constants.ENV_CLIENT_ID: 'client',
                            constants.ENV_CLIENT_SECRET: 'secret',
                            constants.ENV_USE_MSI: 'true',
                            constants.ENV_ACCESS_TOKEN: 'access_token',
                            constants.ENV_KEYVAULT_CLIENT_ID: 'kv_client',
                            constants.ENV_KEYVAULT_SECRET_ID: 'kv_secret'
                        }, clear=True):
            env_params = Session().auth_params

        file_params = Session(authorization_file=self.authorization_file_full).auth_params

        self.assertTrue(env_params.pop('enable_cli_auth'))
        self.assertFalse(file_params.pop('enable_cli_auth', None))
        self.assertEqual(env_params, file_params)

    @patch('c7n_azure.utils.get_keyvault_secret',
           return_value='{"client_id": "client", "client_secret": "secret"}')
    def test_kv_patch(self, _1):
        reload(sys.modules['c7n_azure.session'])
        with patch.dict(os.environ,
                        {
                            constants.ENV_TENANT_ID: 'tenant',
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                            constants.ENV_KEYVAULT_CLIENT_ID: 'kv_client',
                            constants.ENV_KEYVAULT_SECRET_ID: 'kv_secret'
                        }, clear=True):
            with patch('azure.common.credentials.ServicePrincipalCredentials.__init__',
                       autospec=True, return_value=None):
                auth_params = Session().auth_params
            self.assertEqual(auth_params.get('tenant_id'), 'tenant')
            self.assertEqual(auth_params.get('subscription_id'), DEFAULT_SUBSCRIPTION_ID)
            self.assertEqual(auth_params.get('keyvault_client_id'), 'kv_client')
            self.assertEqual(auth_params.get('keyvault_secret_id'), 'kv_secret')
            self.assertEqual(auth_params.get('client_id'), 'client')
            self.assertEqual(auth_params.get('client_secret'), 'secret')
