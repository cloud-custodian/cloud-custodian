# Copyright 2018 Capital One Services, LLC
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

import importlib
import inspect
import json
import logging
import os
import sys
import types

import jwt
from azure.common.credentials import (BasicTokenAuthentication,
                                      ServicePrincipalCredentials)
from azure.keyvault import KeyVaultAuthentication, AccessToken
from c7n_azure import constants
from c7n_azure.utils import (ResourceIdParser, StringUtils, custodian_azure_send_override,
                             ManagedGroupHelper, get_keyvault_secret)
from msrest.exceptions import AuthenticationError
from msrestazure.azure_active_directory import MSIAuthentication
from requests import HTTPError

try:
    from azure.cli.core._profile import Profile
    from knack.util import CLIError
except Exception:
    Profile = None
    CLIError = ImportError  # Assign an exception that never happens because of Auth problems


log = logging.getLogger('custodian.azure.session')


class Session(object):

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
        self._is_token_auth = False
        self._is_cli_auth = False
        self.authorization_file = authorization_file
        self._auth_params = {}

    @property
    def auth_params(self):
        self._initialize_session()
        return self._auth_params

    def _authenticate(self):
        try:
            keyvault_client_id = self._auth_params.get('keyvault_client_id')
            keyvault_secret_id = self._auth_params.get('keyvault_secret_id')

            # If user provided KeyVault secret, we will pull auth params information from it
            if keyvault_secret_id:
                self._auth_params.update(
                    json.loads(
                        get_keyvault_secret(keyvault_client_id, keyvault_secret_id)))

            client_id = self._auth_params.get('client_id')
            client_secret = self._auth_params.get('client_secret')
            access_token = self._auth_params.get('access_token')
            tenant_id = self._auth_params.get('tenant_id')
            use_msi = self._auth_params.get('use_msi')
            subscription_id = self._auth_params.get('subscription_id')

            if access_token and subscription_id:
                log.info("Creating session with Token Authentication")
                self.subscription_id = subscription_id
                self.credentials = BasicTokenAuthentication(
                    token={
                        'access_token': access_token
                    })
                self._is_token_auth = True

            elif client_id and client_secret and tenant_id and subscription_id:
                log.info("Creating session with Service Principal Authentication")
                self.subscription_id = subscription_id
                self.credentials = ServicePrincipalCredentials(
                    client_id=client_id,
                    secret=client_secret,
                    tenant=tenant_id,
                    resource=self.resource_namespace)
                self.tenant_id = tenant_id

            elif use_msi and subscription_id:
                log.info("Creating session with MSI Authentication")
                self.subscription_id = subscription_id
                if client_id:
                    self.credentials = MSIAuthentication(
                        client_id=client_id,
                        resource=self.resource_namespace)
                else:
                    self.credentials = MSIAuthentication(
                        resource=self.resource_namespace)

            elif self._auth_params.get('enable_cli_auth'):
                log.info("Creating session with Azure CLI Authentication")
                self._is_cli_auth = True
                (self.credentials,
                 self.subscription_id,
                 self.tenant_id) = Profile().get_login_credentials(
                    resource=self.resource_namespace)
            log.info("Session using Subscription ID: %s" % self.subscription_id)

        except AuthenticationError as e:
            log.error('Azure Authentication Failure\n'
                      'Error: {0}'
                      .format(json.dumps(e.inner_exception.error_response, indent=2)))
            sys.exit(1)
        except HTTPError as e:
            if keyvault_client_id and keyvault_secret_id:
                log.error('Azure Authentication Failure\n'
                          'Error: Cannot retrieve SP credentials from the Key Vault '
                          '(KV uses MSI to access) with client id: {0}'
                          .format(keyvault_client_id))
            elif use_msi:
                log.error('Azure Authentication Failure\n'
                          'Error: Could not authenticate using managed service identity {0}'
                          .format(client_id if client_id else '(system identity)'))
            else:
                log.error('Azure Authentication Failure: %s' % e.response)
            sys.exit(1)
        except CLIError as e:
            log.error('Azure Authentication Failure\n'
                      'Error: Could not authenticate with Azure CLI credentials: {0}'
                      .format(e))
            sys.exit(1)
        except Exception as e:
            log.error('Azure Authentication Failure\n'
                      'Error: {0}'.format(e))
            sys.exit(1)

    def _initialize_session(self):
        """
        Creates a session using available authentication type.

        Auth priority:
        1. Token Auth
        2. Tenant Auth
        3. Azure CLI Auth

        """

        # Only run once
        if self.credentials is not None:
            return

        if self.authorization_file:
            log.info("Using file for authentication parameters")
            with open(self.authorization_file) as json_file:
                self._auth_params = json.load(json_file)
        else:
            log.info("Using environment variables for authentication parameters")
            self._auth_params = {
                'client_id': os.environ.get(constants.ENV_CLIENT_ID),
                'client_secret': os.environ.get(constants.ENV_CLIENT_SECRET),
                'access_token': os.environ.get(constants.ENV_ACCESS_TOKEN),
                'tenant_id': os.environ.get(constants.ENV_TENANT_ID),
                'use_msi': bool(os.environ.get(constants.ENV_USE_MSI)),
                'subscription_id': os.environ.get(constants.ENV_SUB_ID),
                'keyvault_client_id': os.environ.get(constants.ENV_KEYVAULT_CLIENT_ID),
                'keyvault_secret_id': os.environ.get(constants.ENV_KEYVAULT_SECRET_ID),
                'enable_cli_auth': True
            }

        # Let provided id parameter override everything else
        if self.subscription_id_override is not None:
            self._auth_params['subscription_id'] = self.subscription_id_override

        self._authenticate()

        if self.credentials is None:
            log.error('Unable to authenticate with Azure.')
            sys.exit(1)

        # TODO: cleanup this workaround when issue resolved.
        # https://github.com/Azure/azure-sdk-for-python/issues/5096
        if self.resource_namespace == constants.RESOURCE_VAULT:
            access_token = AccessToken(token=self.get_bearer_token())
            self.credentials = KeyVaultAuthentication(lambda _1, _2, _3: access_token)

    def get_session_for_resource(self, resource):
        return Session(
            subscription_id=self.subscription_id_override,
            authorization_file=self.authorization_file,
            resource=resource)

    def client(self, client):
        self._initialize_session()
        service_name, client_name = client.rsplit('.', 1)
        svc_module = importlib.import_module(service_name)
        klass = getattr(svc_module, client_name)

        klass_parameters = None
        if sys.version_info[0] < 3:
            import funcsigs
            klass_parameters = funcsigs.signature(klass).parameters
        else:
            klass_parameters = inspect.signature(klass).parameters

        client = None
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
        if self._is_token_auth:
            decoded = jwt.decode(self.credentials.token['access_token'], verify=False)
            return decoded['tid']

        return self.tenant_id

    def get_bearer_token(self):
        self._initialize_session()
        if self._is_cli_auth:
            return self.credentials._token_retriever()[1]
        return self.credentials.token['access_token']

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
        """
        Build auth json string for deploying
        Azure Functions.  Look for dedicated
        Functions environment variables or
        fall back to normal Service Principal
        variables.

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
