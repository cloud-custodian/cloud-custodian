# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import importlib
import inspect
import json
import logging
import os
import sys
import types

from azure.common.credentials import BasicTokenAuthentication
from azure.core.credentials import AccessToken
from azure.identity import (AzureCliCredential, ClientSecretCredential,
                            ManagedIdentityCredential, CertificateCredential)
from azure.identity._credentials.azure_cli import _run_command
from msrestazure.azure_cloud import AZURE_PUBLIC_CLOUD
from requests import HTTPError

from c7n_azure import constants
from c7n_azure.utils import (C7nRetryPolicy, ManagedGroupHelper,
                             ResourceIdParser, StringUtils,
                             cost_query_override_api_version,
                             custodian_azure_send_override,
                             get_keyvault_auth_endpoint, get_keyvault_secret,
                             log_response_data)

from functools import lru_cache

log = logging.getLogger('custodian.azure.session')


class AzureCredential:
    def __init__(self, cloud_endpoints, authorization_file=None, subscription_id_override=None):
        # type: (*str, *str) -> None

        if authorization_file:
            with open(authorization_file) as json_file:
                self._auth_params = json.load(json_file)
        else:
            self._auth_params = {
                'client_id': os.environ.get(constants.ENV_CLIENT_ID),
                'client_secret': os.environ.get(constants.ENV_CLIENT_SECRET),
                'access_token': os.environ.get(constants.ENV_ACCESS_TOKEN),
                'tenant_id': os.environ.get(constants.ENV_TENANT_ID),
                'use_msi': bool(os.environ.get(constants.ENV_USE_MSI)),
                'subscription_id': os.environ.get(constants.ENV_SUB_ID),
                'keyvault_client_id': os.environ.get(constants.ENV_KEYVAULT_CLIENT_ID),
                'keyvault_secret_id': os.environ.get(constants.ENV_KEYVAULT_SECRET_ID),
                'client_certificate_path': os.environ.get(
                    constants.ENV_CLIENT_CERTIFICATE_PATH),
                'client_certificate_password': os.environ.get(
                    constants.ENV_CLIENT_CERTIFICATE_PASSWORD),
                'enable_cli_auth': True
            }

        self._auth_params['authority'] = cloud_endpoints.endpoints.active_directory

        keyvault_client_id = self._auth_params.get('keyvault_client_id')
        keyvault_secret_id = self._auth_params.get('keyvault_secret_id')

        # If user provided KeyVault secret, we will pull auth params information from it
        try:
            if keyvault_secret_id:
                self._auth_params.update(
                    json.loads(
                        get_keyvault_secret(
                            keyvault_client_id,
                            keyvault_secret_id)
                    ))
        except HTTPError as e:
            e.message = 'Failed to retrieve SP credential ' \
                        'from Key Vault with client id: {0}'.format(keyvault_client_id)
            raise

        self._credential = None
        if self._auth_params.get('access_token') is not None:
            auth_name = 'Access Token'
            pass
        elif (self._auth_params.get('client_id') and
              self._auth_params.get('client_secret') and
              self._auth_params.get('tenant_id')
              ):
            auth_name = 'Principal'
            self._credential = ClientSecretCredential(
                client_id=self._auth_params['client_id'],
                client_secret=self._auth_params['client_secret'],
                tenant_id=self._auth_params['tenant_id'],
                authority=self._auth_params['authority'])
        elif (self._auth_params.get('client_id') and
              self._auth_params.get('tenant_id') and
              self._auth_params.get('client_certificate_path')):
            auth_name = 'Certificate'
            self._credential = CertificateCredential(
                client_id=self._auth_params['client_id'],
                tenant_id=self._auth_params['tenant_id'],
                certificate_path=self._auth_params['client_certificate_path'],
                password=self._auth_params['client_certificate_password'],
            )
        elif self._auth_params.get('use_msi'):
            auth_name = 'MSI'
            self._credential = ManagedIdentityCredential(
                client_id=self._auth_params.get('client_id'))
        elif self._auth_params.get('enable_cli_auth'):
            auth_name = 'Azure CLI'
            self._credential = AzureCliCredential()
            account_info = _run_command('az account show --output json', timeout=10)
            account_json = json.loads(account_info)
            self._auth_params['subscription_id'] = account_json['id']
            self._auth_params['tenant_id'] = account_json['tenantId']

        if subscription_id_override is not None:
            self._auth_params['subscription_id'] = subscription_id_override

        self._subscription_id = self._auth_params['subscription_id']
        self._tenant_id = self._auth_params['tenant_id']
        log.info('Authenticated [%s | %s%s]',
                 auth_name, self.subscription_id,
                 ' | Authorization File' if authorization_file else '')

    def get_token(self, *scopes, **kwargs):
        # Access Token is used only in tests realistically because
        # KeyVault, Storage and mgmt plane requires separate tokens.
        # TODO: Should we scope this to tests only?
        if (self._auth_params.get('access_token')):
            return AccessToken(self._auth_params['access_token'], expires_on=0)
        try:
            return self._credential.get_token(*scopes, **kwargs)
        except Exception as e:
            log.error('Failed to authenticate.\nMessage: {}'.format(e))
            exit(1)

    # This is temporary until all SDKs we use are upgraded to Track 2
    # List of legacy users:
    #  - DNS
    #  - Record Set (uses DNS SDK)
    #  - Azure Graph
    def legacy_credentials(self, scope):
        # Track 2 SDKs use tuple
        token = self.get_token((scope + '.default'))
        return BasicTokenAuthentication(token={'access_token': token.token})

    @property
    def tenant_id(self):
        # type: (None) -> str
        return self._tenant_id

    @property
    def auth_params(self):
        # type: (None) -> str
        return self._auth_params

    @property
    def subscription_id(self):
        # type: (None) -> str
        return self._subscription_id


class Session:

    def __init__(self, subscription_id=None, authorization_file=None,
                 cloud_endpoints=None, resource_endpoint_type=constants.DEFAULT_AUTH_ENDPOINT):
        """
        :param subscription_id: If provided overrides environment variables.
        :param authorization_file: Path to file populated from 'get_functions_auth_string'
        :param cloud_endpoints: List of endpoints for specified Azure Cloud. Defaults to public.
        :param auth_endpoint: Resource endpoint for OAuth token.
        """
        self._provider_cache = {}
        self.subscription_id_override = subscription_id
        self.credentials = None
        self.authorization_file = authorization_file

        self.cloud_endpoints = cloud_endpoints or AZURE_PUBLIC_CLOUD
        self.resource_endpoint_type = resource_endpoint_type
        self.resource_endpoint = self.get_auth_endpoint(resource_endpoint_type)
        self.storage_endpoint = self.cloud_endpoints.suffixes.storage_endpoint

    def _initialize_session(self):
        """
        Creates a session using available authentication type.
        """

        # Only run once
        if self.credentials is not None:
            return

        try:
            self.credentials = AzureCredential(
                self.cloud_endpoints,
                authorization_file=self.authorization_file,
                subscription_id_override=self.subscription_id_override)
        except Exception as e:
            if hasattr(e, 'message'):
                log.error(e.message)
            else:
                log.exception("Failed to authenticate.")
            sys.exit(1)

        if self.credentials is None:
            log.error('Failed to authenticate.')
            sys.exit(1)

    def get_session_for_resource(self, resource):
        return Session(
            subscription_id=self.subscription_id_override,
            authorization_file=self.authorization_file,
            cloud_endpoints=self.cloud_endpoints,
            resource_endpoint_type=resource)

    @lru_cache()
    def client(self, client, vault_url=None):
        self._initialize_session()
        service_name, client_name = client.rsplit('.', 1)
        svc_module = importlib.import_module(service_name)
        klass = getattr(svc_module, client_name)

        klass_parameters = inspect.signature(klass).parameters

        legacy = False

        if 'credentials' in klass_parameters and 'tenant_id' in klass_parameters:
            client = klass(credentials=self.credentials.legacy_credentials(self.resource_endpoint),
                           tenant_id=self.credentials.tenant_id,
                           base_url=self.resource_endpoint)
            legacy = True
        elif 'credentials' in klass_parameters:
            client = klass(credentials=self.credentials.legacy_credentials(self.resource_endpoint),
                           subscription_id=self.credentials.subscription_id,
                           base_url=self.cloud_endpoints.endpoints.resource_manager)
            legacy = True
        else:
            client_args = {
                'credential': self.credentials,
                'raw_response_hook': log_response_data,
                'retry_policy': C7nRetryPolicy(),
                'credential_scopes': [self.resource_endpoint + ".default"]
            }

            # TODO: remove when fixed: https://github.com/Azure/azure-sdk-for-python/issues/17351
            # This workaround will replace used api-version for costmanagement requests
            # 2020-06-01 is not supported, but 2019-11-01 is working as expected.
            if client == 'azure.mgmt.costmanagement.CostManagementClient':
                client_args['raw_request_hook'] = cost_query_override_api_version

            if 'subscription_id' in klass_parameters:
                client_args['subscription_id'] = self.subscription_id
                client_args['base_url'] = self.cloud_endpoints.endpoints.resource_manager
            elif 'vault_url' in klass_parameters:
                client_args['vault_url'] = vault_url
            client = klass(**client_args)

        if legacy:
            # Override send() method to log request limits & custom retries
            service_client = client._client
            service_client.orig_send = service_client.send
            service_client.send = types.MethodType(custodian_azure_send_override, service_client)

            # Don't respect retry_after_header to implement custom retries
            service_client.config.retry_policy.policy.respect_retry_after_header = False

        return client

    @property
    def subscription_id(self):
        self._initialize_session()
        return self.credentials.subscription_id

    def get_credentials(self):
        self._initialize_session()
        return self.credentials

    def get_subscription_id(self):
        self._initialize_session()
        return self.credentials.subscription_id

    def get_function_target_subscription_name(self):
        self._initialize_session()

        if constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME in os.environ:
            return os.environ[constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME]
        return os.environ.get(constants.ENV_FUNCTION_SUB_ID, self.subscription_id)

    def get_function_target_subscription_ids(self):
        self._initialize_session()

        if constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME in os.environ:
            return ManagedGroupHelper.get_subscriptions_list(
                os.environ[constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME], self)

        return [os.environ.get(constants.ENV_FUNCTION_SUB_ID, self.subscription_id)]

    def resource_api_version(self, resource_id):
        """ latest non-preview api version for resource """

        namespace = ResourceIdParser.get_namespace(resource_id)
        resource_type = ResourceIdParser.get_resource_type(resource_id)

        cache_id = namespace + resource_type

        if cache_id in self._provider_cache:
            return self._provider_cache[cache_id]

        resource_client = self.client('azure.mgmt.resource.ResourceManagementClient')
        provider = resource_client.providers.get(namespace)

        # The api version may be directly provided
        if not provider.resource_types and resource_client.providers.api_version:
            return resource_client.providers.api_version

        rt = next((t for t in provider.resource_types
                   if StringUtils.equal(t.resource_type, resource_type)), None)

        if rt and rt.api_versions:
            versions = [v for v in rt.api_versions if 'preview' not in v.lower()]
            api_version = versions[0] if versions else rt.api_versions[0]
            self._provider_cache[cache_id] = api_version
            return api_version

    def get_tenant_id(self):
        self._initialize_session()
        return self.credentials.tenant_id

    def get_functions_auth_string(self, target_subscription_id):
        """Build auth json string for deploying Azure Functions.

        Look for dedicated Functions environment variables or fall
        back to normal Service Principal variables.
        """

        self._initialize_session()

        function_auth_variables = [
            constants.ENV_FUNCTION_TENANT_ID,
            constants.ENV_FUNCTION_CLIENT_ID,
            constants.ENV_FUNCTION_CLIENT_SECRET
        ]

        required_params = ['client_id', 'client_secret', 'tenant_id']

        function_auth_params = {k: v for k, v in self.credentials.auth_params.items()
                                if k in required_params and v is not None}
        function_auth_params['subscription_id'] = target_subscription_id

        # Use dedicated function env vars if available
        if all(k in os.environ for k in function_auth_variables):
            function_auth_params['client_id'] = os.environ[constants.ENV_FUNCTION_CLIENT_ID]
            function_auth_params['client_secret'] = os.environ[constants.ENV_FUNCTION_CLIENT_SECRET]
            function_auth_params['tenant_id'] = os.environ[constants.ENV_FUNCTION_TENANT_ID]

        # Verify SP authentication parameters
        if any(k not in function_auth_params.keys() for k in required_params):
            raise NotImplementedError(
                "Service Principal credentials are the only "
                "supported auth mechanism for deploying functions.")

        return json.dumps(function_auth_params, indent=2)

    def get_auth_endpoint(self, endpoint):
        if endpoint == constants.VAULT_AUTH_ENDPOINT:
            return get_keyvault_auth_endpoint(self.cloud_endpoints)

        elif endpoint == constants.STORAGE_AUTH_ENDPOINT:
            # These endpoints are not Cloud specific, but the suffixes are
            return constants.STORAGE_AUTH_ENDPOINT
        else:
            return getattr(self.cloud_endpoints.endpoints, endpoint)
