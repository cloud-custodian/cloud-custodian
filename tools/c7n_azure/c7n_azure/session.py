# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import abc
import importlib
import inspect
import json
import logging
import os
import sys
import types
from collections import namedtuple

from azure.common.credentials import (BasicTokenAuthentication,
                                      ServicePrincipalCredentials)
from azure.keyvault import KeyVaultAuthentication, AccessToken
import jwt
from msrest.exceptions import AuthenticationError
from msrestazure.azure_active_directory import MSIAuthentication
from requests import HTTPError

from c7n_azure import constants
from c7n_azure.utils import (ResourceIdParser, StringUtils, custodian_azure_send_override,
                             ManagedGroupHelper, get_keyvault_secret)


try:
    from azure.cli.core._profile import Profile
    from knack.util import CLIError
except Exception:
    Profile = None
    CLIError = ImportError  # Assign an exception that never happens because of Auth problems

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache


log = logging.getLogger('custodian.azure.session')


class Session:

    def __init__(self, subscription_id=None, authorization_file=None,
                 resource=constants.RESOURCE_ACTIVE_DIRECTORY):
        """
        :param subscription_id: If provided overrides environment variables.
        :param authorization_file: Path to file populated from 'get_functions_auth_string'
        :param resource: Resource endpoint for OAuth token.
        """

        self._provider_cache = {}
        self.subscription_id_override = subscription_id
        self.credentials = None
        self.subscription_id = None
        self.tenant_id = None
        self.resource_namespace = resource
        self.authorization_file = authorization_file
        self._auth_params = {}

    @property
    def auth_params(self):
        self._initialize_session()
        return self._auth_params

    def _authenticate(self):
        keyvault_client_id = self._auth_params.get('keyvault_client_id')
        keyvault_secret_id = self._auth_params.get('keyvault_secret_id')

        # If user provided KeyVault secret, we will pull auth params information from it
        try:
            if keyvault_secret_id:
                self._auth_params.update(
                    json.loads(
                        get_keyvault_secret(keyvault_client_id, keyvault_secret_id)))
        except HTTPError as e:
            e.message = 'Failed to retrieve SP credential ' \
                        'from Key Vault with client id: {0}'.format(keyvault_client_id)
            raise

        token_providers = [
            AccessTokenProvider,
            ServicePrincipalProvider,
            MSIProvider,
            CLIProvider
        ]

        for provider in token_providers:
            instance = provider(self._auth_params, self.resource_namespace)
            if instance.is_available():
                result = instance.authenticate()
                self.subscription_id = result.subscription_id
                self.tenant_id = result.tenant_id
                self.credentials = result.credential
                self.token_provider = provider
                break

        # Let provided id parameter override everything else
        if self.subscription_id_override is not None:
            self.subscription_id = self.subscription_id_override

        log.info('Authenticated [%s | %s%s]',
                 instance.name, self.subscription_id,
                 ' | Authorization File' if self.authorization_file else '')

    def _initialize_session(self):
        """
        Creates a session using available authentication type.
        """

        # Only run once
        if self.credentials is not None:
            return

        if self.authorization_file:
            with open(self.authorization_file) as json_file:
                self._auth_params = json.load(json_file)
            if self.subscription_id_override is not None:
                self._auth_params['subscription_id'] = self.subscription_id_override
        else:
            self._auth_params = {
                'client_id': os.environ.get(constants.ENV_CLIENT_ID),
                'client_secret': os.environ.get(constants.ENV_CLIENT_SECRET),
                'access_token': os.environ.get(constants.ENV_ACCESS_TOKEN),
                'tenant_id': os.environ.get(constants.ENV_TENANT_ID),
                'use_msi': bool(os.environ.get(constants.ENV_USE_MSI)),
                'subscription_id':
                    self.subscription_id_override or os.environ.get(constants.ENV_SUB_ID),
                'keyvault_client_id': os.environ.get(constants.ENV_KEYVAULT_CLIENT_ID),
                'keyvault_secret_id': os.environ.get(constants.ENV_KEYVAULT_SECRET_ID),
                'enable_cli_auth': True
            }

        try:
            self._authenticate()
        except Exception as e:
            if hasattr(e, 'message'):
                log.error(e.message)
            else:
                log.exception("Failed to authenticate.")
            sys.exit(1)

        if self.credentials is None:
            log.error('Failed to authenticate.')
            sys.exit(1)

        # Override credential type for KV auth
        # https://github.com/Azure/azure-sdk-for-python/issues/5096
        if self.resource_namespace == constants.RESOURCE_VAULT:
            access_token = AccessToken(token=self.get_bearer_token())
            self.credentials = KeyVaultAuthentication(lambda _1, _2, _3: access_token)

    def get_session_for_resource(self, resource):
        return Session(
            subscription_id=self.subscription_id_override,
            authorization_file=self.authorization_file,
            resource=resource)

    @lru_cache()
    def client(self, client):
        self._initialize_session()
        service_name, client_name = client.rsplit('.', 1)
        svc_module = importlib.import_module(service_name)
        klass = getattr(svc_module, client_name)

        klass_parameters = inspect.signature(klass).parameters

        if 'subscription_id' in klass_parameters:
            client = klass(credentials=self.credentials, subscription_id=self.subscription_id)
        else:
            client = klass(credentials=self.credentials)

        # Override send() method to log request limits & custom retries
        service_client = client._client
        service_client.orig_send = service_client.send
        service_client.send = types.MethodType(custodian_azure_send_override, service_client)

        # Don't respect retry_after_header to implement custom retries
        service_client.config.retry_policy.policy.respect_retry_after_header = False

        return client

    def get_credentials(self):
        self._initialize_session()
        return self.credentials

    def get_subscription_id(self):
        self._initialize_session()
        return self.subscription_id

    def get_function_target_subscription_name(self):
        self._initialize_session()

        if constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME in os.environ:
            return os.environ[constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME]
        return os.environ.get(constants.ENV_FUNCTION_SUB_ID, self.subscription_id)

    def get_function_target_subscription_ids(self):
        self._initialize_session()

        if constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME in os.environ:
            return ManagedGroupHelper.get_subscriptions_list(
                os.environ[constants.ENV_FUNCTION_MANAGEMENT_GROUP_NAME], self.get_credentials())

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
        return self.tenant_id

    def get_bearer_token(self):
        self._initialize_session()
        return self.token_provider.get_bearer_token(self.credentials)

    def load_auth_file(self, path):
        with open(path) as json_file:
            data = json.load(json_file)
            self.tenant_id = data['credentials']['tenant']
            return (ServicePrincipalCredentials(
                client_id=data['credentials']['client_id'],
                secret=data['credentials']['secret'],
                tenant=self.tenant_id,
                resource=self.resource_namespace
            ), data.get('subscription', None))

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

        function_auth_params = {k: v for k, v in self._auth_params.items()
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


class TokenProvider(metaclass=abc.ABCMeta):
    AuthenticationResult = namedtuple(
        'AuthenticationResult', 'credential, subscription_id, tenant_id')

    def __init__(self, parameters, namespace):
        # type: (dict, str) -> None
        self.parameters = parameters
        self.resource_namespace = namespace

    @abc.abstractmethod
    def is_available(self):
        # type: () -> bool
        raise NotImplementedError()

    @abc.abstractmethod
    def authenticate(self):
        # type: () -> TokenProvider.AuthenticationResult
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def name(self):
        # type: () -> str
        raise NotImplementedError()

    @staticmethod
    def get_bearer_token(token):
        return token.token['access_token']


class CLIProvider(TokenProvider):
    def is_available(self):
        # type: () -> bool
        return self.parameters.get('enable_cli_auth', False)

    def authenticate(self):
        # type: () -> TokenProvider.AuthenticationResult

        try:
            (credential,
             subscription_id,
             tenant_id) = Profile().get_login_credentials(resource=self.resource_namespace)
        except CLIError as e:
            e.message = 'Failed to authenticate with CLI credentials. ' + e.args[0]
            raise

        return TokenProvider.AuthenticationResult(
            credential=credential,
            subscription_id=subscription_id,
            tenant_id=tenant_id
        )

    @property
    def name(self):
        # type: () -> str
        return "Azure CLI"

    @staticmethod
    def get_bearer_token(token):
        return token._token_retriever()[1]


class AccessTokenProvider(TokenProvider):
    def __init__(self, parameters, namespace):
        super(AccessTokenProvider, self).__init__(parameters, namespace)
        self.subscription_id = self.parameters.get('subscription_id')
        self.access_token = self.parameters.get('access_token')

    def is_available(self):
        # type: () -> bool
        return self.access_token and self.subscription_id

    def authenticate(self):
        # type: () -> TokenProvider.AuthenticationResult
        credential = BasicTokenAuthentication(token={'access_token': self.access_token})

        decoded = jwt.decode(credential.token['access_token'], verify=False)

        return TokenProvider.AuthenticationResult(
            credential=credential,
            subscription_id=self.subscription_id,
            tenant_id=decoded['tid']
        )

    @property
    def name(self):
        # type: () -> str
        return "Access Token"


class ServicePrincipalProvider(TokenProvider):
    def __init__(self, parameters, namespace):
        super(ServicePrincipalProvider, self).__init__(parameters, namespace)
        self.client_id = self.parameters.get('client_id')
        self.client_secret = self.parameters.get('client_secret')
        self.tenant_id = self.parameters.get('tenant_id')
        self.subscription_id = self.parameters.get('subscription_id')

    def is_available(self):
        # type: () -> bool
        return (self.client_id and
                self.client_secret and
                self.tenant_id and
                self.subscription_id)

    def authenticate(self):
        # type: () -> TokenProvider.AuthenticationResult
        try:
            credential = ServicePrincipalCredentials(client_id=self.client_id,
                                                secret=self.client_secret,
                                                tenant=self.tenant_id,
                                                resource=self.resource_namespace)
        except AuthenticationError as e:
            e.message = 'Failed to authenticate with service principal.\n'\
                        'Message: {0}'.format(
                            json.dumps(e.inner_exception.error_response, indent=2))
            raise

        return TokenProvider.AuthenticationResult(
            credential=credential,
            subscription_id=self.subscription_id,
            tenant_id=self.tenant_id
        )

    @property
    def name(self):
        # type: () -> str
        return "Principal"


class MSIProvider(TokenProvider):
    def __init__(self, parameters, namespace):
        super(MSIProvider, self).__init__(parameters, namespace)
        self.client_id = self.parameters.get('client_id')
        self.use_msi = self.parameters.get('use_msi')
        self.subscription_id = self.parameters.get('subscription_id')

    def is_available(self):
        # type: () -> bool
        return self.use_msi and self.subscription_id

    def authenticate(self):
        # type: () -> TokenProvider.AuthenticationResult
        try:
            if self.client_id:
                credential = MSIAuthentication(
                    client_id=self.client_id,
                    resource=self.resource_namespace)
            else:
                credential = MSIAuthentication(
                    resource=self.resource_namespace)
        except HTTPError as e:
            e.message = 'Failed to authenticate with MSI'
            raise

        return TokenProvider.AuthenticationResult(
            credential=credential,
            subscription_id=self.subscription_id,
            tenant_id=None
        )

    @property
    def name(self):
        # type: () -> str
        return "MSI"
