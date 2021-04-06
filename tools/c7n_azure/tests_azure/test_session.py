# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
import re
import sys
from importlib import reload

import pytest
from adal import AdalError
from azure.core.credentials import AccessToken
from azure.identity import (ClientSecretCredential, ManagedIdentityCredential)
from c7n_azure import constants
from c7n_azure.session import Session
from mock import patch
from msrest.exceptions import AuthenticationError
from msrestazure.azure_cloud import AZURE_CHINA_CLOUD
from requests import HTTPError

from .azure_common import DEFAULT_SUBSCRIPTION_ID, DEFAULT_TENANT_ID, BaseTest

CUSTOM_SUBSCRIPTION_ID = '00000000-5106-4743-99b0-c129bfa71a47'


class SessionTest(BaseTest):
    authorization_file = os.path.join(os.path.dirname(__file__), 'data', 'test_auth_file.json')
    authorization_file_kv = os.path.join(os.path.dirname(__file__), 'data',
                                         'test_auth_file_kv.json')
    authorization_file_full = os.path.join(os.path.dirname(__file__),
                                           'data',
                                           'test_auth_file_full.json')
    authorization_file_no_sub = os.path.join(os.path.dirname(__file__),
                                           'data',
                                           'test_auth_file_no_sub.json')

    def setUp(self):
        super(SessionTest, self).setUp()

    def tearDown(self):
        super(SessionTest, self).tearDown()
        reload(sys.modules['c7n_azure.session'])

    def mock_init(self, client_id, secret, tenant, resource):
        pass

    def test_initialize_session_auth_file(self):
        s = Session(authorization_file=self.authorization_file)

        self.assertIs(type(s.get_credentials()._credential), ClientSecretCredential)
        self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)
        self.assertEqual(s.get_tenant_id(), 'tenant')

    def test_initialize_session_auth_file_custom_subscription(self):
        s = Session(subscription_id=CUSTOM_SUBSCRIPTION_ID,
                    authorization_file=self.authorization_file)

        self.assertIs(type(s.get_credentials()._credential), ClientSecretCredential)
        self.assertEqual(s.get_subscription_id(), CUSTOM_SUBSCRIPTION_ID)

        # will vary between recorded/live auth options but useful to ensure
        # we ended up with one of the valid values
        self.assertTrue(s.get_tenant_id() in [DEFAULT_TENANT_ID, 'tenant'])

    def test_initialize_session_auth_file_no_sub(self):
        s = Session(subscription_id=CUSTOM_SUBSCRIPTION_ID,
                    authorization_file=self.authorization_file_no_sub)

        self.assertIs(type(s.get_credentials()._credential), ClientSecretCredential)
        self.assertEqual(s.get_subscription_id(), CUSTOM_SUBSCRIPTION_ID)

        # will vary between recorded/live auth options but useful to ensure
        # we ended up with one of the valid values
        self.assertTrue(s.get_tenant_id() in [DEFAULT_TENANT_ID, 'tenant'])

    def test_initialize_session_principal(self):
        with patch.dict(os.environ,
                        {
                            constants.ENV_TENANT_ID: DEFAULT_TENANT_ID,
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                            constants.ENV_CLIENT_ID: 'client',
                            constants.ENV_CLIENT_SECRET: 'secret'
                        }, clear=True):
            s = Session()

            self.assertIs(type(s.get_credentials()._credential), ClientSecretCredential)
            self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)
            self.assertEqual(s.get_tenant_id(), DEFAULT_TENANT_ID)

    @patch('azure.identity.ClientSecretCredential.get_token')
    @patch('c7n_azure.session.log.error')
    def test_initialize_session_authentication_error(self, mock_log, mock_cred):
        with self.assertRaises(SystemExit):
            adal_err = AdalError("test")
            adal_err.error_response = {'error': 'test'}
            err = AuthenticationError('test')
            err.inner_exception = adal_err
            mock_cred.side_effect = err

            with patch.dict(os.environ,
                            {
                                constants.ENV_TENANT_ID: DEFAULT_TENANT_ID,
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                                constants.ENV_CLIENT_ID: 'client',
                                constants.ENV_CLIENT_SECRET: 'secret'
                            }, clear=True):
                s = Session()
                s.get_credentials().get_token()

        mock_log.assert_called_once()

    def test_initialize_msi_auth_system(self):
        with patch.dict(os.environ,
                        {
                            constants.ENV_USE_MSI: 'true',
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID
                        }, clear=True):
            s = Session()

            self.assertIsInstance(s.get_credentials()._credential, ManagedIdentityCredential)
            self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)

    def test_initialize_msi_auth_user(self):
        with patch.dict(os.environ,
                        {
                            constants.ENV_USE_MSI: 'true',
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                            constants.ENV_CLIENT_ID: 'client'
                        }, clear=True):
            s = Session()

            self.assertIsInstance(s.get_credentials()._credential, ManagedIdentityCredential)
            self.assertEqual(
                s.get_credentials()._credential._credential._identity_config["client_id"],
                'client')
            self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)

    @patch('msrestazure.azure_active_directory.MSIAuthentication.__init__')
    @patch('c7n_azure.session.log.error')
    def test_initialize_session_msi_authentication_error(self, mock_log, mock_cred):
        with self.assertRaises(SystemExit):
            mock_cred.side_effect = HTTPError()

            with patch.dict(os.environ,
                            {
                                constants.ENV_USE_MSI: 'true',
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID
                            }, clear=True):
                s = Session()
                s.get_credentials().get_token()

        mock_log.assert_called_once()

    def test_initialize_session_token(self):
        with patch.dict(os.environ,
                        {
                            constants.ENV_ACCESS_TOKEN: 'token',
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID
                        }, clear=True):
            s = Session()

            self.assertIsNone(s.get_credentials()._credential)
            self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)
            self.assertEqual(s.get_credentials().get_token(), AccessToken('token', 0))

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

    # TODO this test has been flakey in ci, disabling temporarily
    def xtest_get_function_target_subscription(self):
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
        resource_session = s.get_session_for_resource(constants.STORAGE_AUTH_ENDPOINT)
        self.assertEqual(resource_session.resource_endpoint, constants.STORAGE_AUTH_ENDPOINT)

    # This test won't run with real credentials unless the
    # tenant is actually in Azure China cloud.
    @pytest.mark.skiplive
    def test_get_client_non_default_base_url(self):
        s = Session(cloud_endpoints=AZURE_CHINA_CLOUD)
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        self.assertEqual(AZURE_CHINA_CLOUD.endpoints.resource_manager,
                         client._client._base_url)

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
            env_params = Session().get_credentials().auth_params

        session = Session(authorization_file=self.authorization_file_full)
        file_params = session.get_credentials().auth_params

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
            auth_params = Session().get_credentials().auth_params
            self.assertEqual(auth_params.get('tenant_id'), 'tenant')
            self.assertEqual(auth_params.get('subscription_id'), DEFAULT_SUBSCRIPTION_ID)
            self.assertEqual(auth_params.get('keyvault_client_id'), 'kv_client')
            self.assertEqual(auth_params.get('keyvault_secret_id'), 'kv_secret')
            self.assertEqual(auth_params.get('client_id'), 'client')
            self.assertEqual(auth_params.get('client_secret'), 'secret')

    @patch('c7n_azure.utils.get_keyvault_secret')
    @patch('c7n_azure.session.log.error')
    def test_initialize_session_kv_authentication_error(self, mock_log, mock_get_kv_secret):
        reload(sys.modules['c7n_azure.session'])

        with self.assertRaises(SystemExit):
            mock_get_kv_secret.side_effect = HTTPError()

            with patch.dict(os.environ,
                            {
                                constants.ENV_TENANT_ID: 'tenant',
                                constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                                constants.ENV_KEYVAULT_CLIENT_ID: 'kv_client',
                                constants.ENV_KEYVAULT_SECRET_ID: 'kv_secret'
                            }, clear=True):
                s = Session()
                s.get_subscription_id()

        mock_log.assert_called_once_with(
            'Failed to retrieve SP credential from '
            'Key Vault with client id: kv_client')

    def test_get_auth_endpoint(self):
        s = Session()
        result = s.get_auth_endpoint(constants.DEFAULT_AUTH_ENDPOINT)
        self.assertEqual('https://management.core.windows.net/', result)

    def test_get_auth_endpoint_vault(self):
        s = Session()
        result = s.get_auth_endpoint(constants.VAULT_AUTH_ENDPOINT)
        self.assertEqual('https://vault.azure.net', result)

    def test_get_auth_endpoint_storage(self):
        s = Session()
        result = s.get_auth_endpoint(constants.STORAGE_AUTH_ENDPOINT)
        self.assertEqual('https://storage.azure.com/', result)

    @patch('c7n_azure.utils.C7nRetryPolicy.__init__', return_value=None)
    def test_retry_policy_override(self, c7n_retry):
        s = Session()
        s.client('azure.mgmt.compute.ComputeManagementClient')
        c7n_retry.assert_called_once()

    @patch('c7n_azure.session.log_response_data', return_value=None)
    def test_log_custom_hook(self, log):
        s = Session()
        client = s.client('azure.mgmt.compute.ComputeManagementClient')
        [v for v in client.virtual_machines.list_all()]
        log.assert_called_once()
