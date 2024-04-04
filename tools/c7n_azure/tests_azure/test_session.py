# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
import re
from inspect import signature
import tempfile
from datetime import datetime, timedelta

import pytest
from adal import AdalError
from azure.core.credentials import AccessToken
from azure.identity import (ClientSecretCredential, ManagedIdentityCredential)
from azure.identity._credentials import azure_cli
from c7n_azure import constants
from c7n_azure.session import Session
from mock import patch
from msrest.exceptions import AuthenticationError
from msrestazure.azure_cloud import (AZURE_CHINA_CLOUD, AZURE_US_GOV_CLOUD)
from requests import HTTPError

from .azure_common import DEFAULT_SUBSCRIPTION_ID, DEFAULT_TENANT_ID, BaseTest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes


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

    def mock_init(self, client_id, secret, tenant, resource):
        pass

    def generate_fake_cert(self, password):
        cn = 'example.com'
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        builder = x509.CertificateBuilder()
        builder = builder.subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        builder = builder.issuer_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        builder = builder.not_valid_before(datetime.utcnow())
        builder = builder.not_valid_after(datetime.utcnow() + timedelta(days=365))
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.public_key(public_key)
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)

        certificate = builder.sign(private_key=private_key, algorithm=hashes.SHA256())

        # serialize our certificate and private key to PEM format
        pem_cert = certificate.public_bytes(serialization.Encoding.PEM)
        pem_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
        )
        return pem_cert + pem_key

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

    @patch('c7n_azure.session._run_command')
    def test_initialize_session_cli(self, mock_run):
        mock_run.return_value = \
            f'{{"id":"{DEFAULT_SUBSCRIPTION_ID}", "tenantId":"{DEFAULT_TENANT_ID}"}}'

        with patch.dict(os.environ, {}, clear=True):
            s = Session()
            self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)
            self.assertEqual(s.get_tenant_id(), DEFAULT_TENANT_ID)

    def test_run_command_signature(self):
        """Catch signature changes in the internal method we use for CLI authentication

        We use _run_command() to fetch default subscription information. This information
        was previously accessible via azure-common but has been deprecated in favor
        of azure-identity:

        https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/identity/azure-identity/migration_guide.md

        It's not clear how to reliably get the CLI's default subscription purely from
        azure-identity (avoiding an explicit azure-cli dependency). Azure CLI docs suggest
        that while we can _usually_ pull default subscription info out of ~/.azure/azureProfile,
        it might be elsewhere:

        https://github.com/Azure/azure-cli/blob/813da51a0a6ac2d427e496f1dffc01c96af24d78/src/azure-cli-core/azure/cli/core/_profile.py#L20-L24

        So continuing to rely on _run_command() may be more reliable, as long as we
        catch signature changes to avoid accidental breakage.
        """
        expected_parameters = {"command", "timeout"}
        actual_parameters = set(signature(azure_cli._run_command).parameters.keys())
        self.assertSetEqual(expected_parameters, actual_parameters)

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
#            self.assertEqual(
#                s.get_credentials()._credential._credential._identity_config["client_id"],
#                'client')
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

    def test_initialize_certificate(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write(self.generate_fake_cert('password'))
            filename = fp.name
        with patch.dict(os.environ,
                        {
                            constants.ENV_TENANT_ID: 'tenant',
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                            constants.ENV_CLIENT_ID: 'client',
                            constants.ENV_CLIENT_CERTIFICATE_PATH: filename,
                            constants.ENV_CLIENT_CERTIFICATE_PASSWORD: 'password'
                        }, clear=True):
            s = Session()
            creds = s.get_credentials()
            self.assertEqual(s.get_subscription_id(), DEFAULT_SUBSCRIPTION_ID)
            self.assertIsNotNone(creds._credential)

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
                with patch('c7n_azure.session.ManagedGroupHelper.get_subscriptions_list',
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
        self.assertEqual(AZURE_CHINA_CLOUD.endpoints.management + ".default",
                         client._client._config.credential_scopes[0])

    # This test won't run with real credentials unless the
    # tenant is actually in Azure US Government
    @pytest.mark.skiplive
    def test_get_client_us_gov(self):
        """Verify we are setting the correct credential scope for us government"""
        s = Session(cloud_endpoints=AZURE_US_GOV_CLOUD)
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        self.assertEqual(AZURE_US_GOV_CLOUD.endpoints.resource_manager,
                         client._client._base_url)
        self.assertEqual(AZURE_US_GOV_CLOUD.endpoints.management + ".default",
                         client._client._config.credential_scopes[0])

    @patch('c7n_azure.session.get_keyvault_secret', return_value='{}')
    def test_compare_auth_params(self, _1):
        with patch.dict(os.environ,
                        {
                            constants.ENV_TENANT_ID: 'tenant',
                            constants.ENV_SUB_ID: DEFAULT_SUBSCRIPTION_ID,
                            constants.ENV_CLIENT_ID: 'client',
                            constants.ENV_CLIENT_SECRET: 'secret',
                            constants.ENV_USE_MSI: 'true',
                            constants.ENV_ACCESS_TOKEN: 'access_token',
                            constants.ENV_KEYVAULT_CLIENT_ID: 'kv_client',
                            constants.ENV_KEYVAULT_SECRET_ID: 'kv_secret',
                            constants.ENV_CLIENT_CERTIFICATE_PATH: '/certificate',
                            constants.ENV_CLIENT_CERTIFICATE_PASSWORD: 'password'
                        }, clear=True):
            env_params = Session().get_credentials().auth_params

        session = Session(authorization_file=self.authorization_file_full)
        file_params = session.get_credentials().auth_params

        self.assertTrue(env_params.pop('enable_cli_auth'))
        self.assertFalse(file_params.pop('enable_cli_auth', None))
        self.assertEqual(env_params, file_params)

    @patch('c7n_azure.session.get_keyvault_secret',
           return_value='{"client_id": "client", "client_secret": "secret"}')
    def test_kv_patch(self, _1):
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

    @patch('c7n_azure.session.get_keyvault_secret')
    @patch('c7n_azure.session.log.error')
    def test_initialize_session_kv_authentication_error(self, mock_log, mock_get_kv_secret):
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

    @patch('c7n_azure.session.C7nRetryPolicy.__init__', return_value=None)
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
