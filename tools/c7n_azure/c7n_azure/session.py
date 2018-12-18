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
import json
import logging
import os

import jwt
from azure.common.credentials import (BasicTokenAuthentication,
                                      ServicePrincipalCredentials)

from msrestazure.azure_active_directory import MSIAuthentication

from c7n_azure import constants
from c7n_azure.utils import ResourceIdParser, StringUtils

try:
    from azure.cli.core._profile import Profile
except Exception:
    Profile = None


class Session(object):

    def __init__(self, subscription_id=None, authorization_file=None,
                 resource=constants.RESOURCE_ACTIVE_DIRECTORY):
        """
        :param subscription_id: If provided overrides environment variables.
        :param authorization_file: Path to file populated from 'get_functions_auth_string'
        :param resource: Resource endpoint for OAuth token.
        """

        self.log = logging.getLogger('custodian.azure.session')
        self._provider_cache = {}
        self.subscription_id_override = subscription_id
        self.credentials = None
        self.subscription_id = None
        self.tenant_id = None
        self.resource_namespace = resource
        self._is_token_auth = False
        self._is_cli_auth = False
        self.authorization_file = authorization_file

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

        tenant_auth_variables = [
            constants.ENV_TENANT_ID, constants.ENV_SUB_ID,
            constants.ENV_CLIENT_ID, constants.ENV_CLIENT_SECRET
        ]

        token_auth_variables = [
            constants.ENV_ACCESS_TOKEN, constants.ENV_SUB_ID
        ]

        msi_auth_variables = [
            constants.ENV_USE_MSI, constants.ENV_SUB_ID
        ]

        if self.authorization_file:
            self.credentials, self.subscription_id = self.load_auth_file(self.authorization_file)
            self.log.info("Creating session with authorization file")

        elif all(k in os.environ for k in token_auth_variables):
            # Token authentication
            self.credentials = BasicTokenAuthentication(
                token={
                    'access_token': os.environ[constants.ENV_ACCESS_TOKEN]
                })
            self.subscription_id = os.environ[constants.ENV_SUB_ID]
            self.log.info("Creating session with Token Authentication")
            self._is_token_auth = True

        elif all(k in os.environ for k in tenant_auth_variables):
            # Tenant (service principal) authentication
            self.credentials = ServicePrincipalCredentials(
                client_id=os.environ[constants.ENV_CLIENT_ID],
                secret=os.environ[constants.ENV_CLIENT_SECRET],
                tenant=os.environ[constants.ENV_TENANT_ID],
                resource=self.resource_namespace)
            self.subscription_id = os.environ[constants.ENV_SUB_ID]
            self.tenant_id = os.environ[constants.ENV_TENANT_ID]
            self.log.info("Creating session with Service Principal Authentication")

        elif all(k in os.environ for k in msi_auth_variables):
            # MSI authentication
            if constants.ENV_CLIENT_ID in os.environ:
                self.credentials = MSIAuthentication(
                    client_id=os.environ[constants.ENV_CLIENT_ID],
                    resource=self.resource_namespace)
            else:
                self.credentials = MSIAuthentication(
                    resource=self.resource_namespace)

            self.subscription_id = os.environ[constants.ENV_SUB_ID]
            self.log.info("Creating session with MSI Authentication")
        else:
            # Azure CLI authentication
            self._is_cli_auth = True
            (self.credentials,
             self.subscription_id,
             self.tenant_id) = Profile().get_login_credentials(
                resource=self.resource_namespace)
            self.log.info("Creating session with Azure CLI Authentication")

        # Let provided id parameter override everything else
        if self.subscription_id_override is not None:
            self.subscription_id = self.subscription_id_override

        self.log.info("Session using Subscription ID: %s" % self.subscription_id)

        if self.credentials is None:
            self.log.error('Unable to locate credentials for Azure session.')

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
        return klass(self.credentials, self.subscription_id)

    def get_credentials(self):
        self._initialize_session()
        return self.credentials

    def get_subscription_id(self):
        self._initialize_session()
        return self.subscription_id

    def get_function_target_subscription_id(self):
        self._initialize_session()
        return os.environ.get(constants.ENV_FUNCTION_SUB_ID, self.subscription_id)

    def resource_api_version(self, resource_id):
        """ latest non-preview api version for resource """

        namespace = ResourceIdParser.get_namespace(resource_id)
        resource_type = ResourceIdParser.get_resource_type(resource_id)

        cache_id = namespace + resource_type

        if cache_id in self._provider_cache:
            return self._provider_cache[cache_id]

        resource_client = self.client('azure.mgmt.resource.ResourceManagementClient')
        provider = resource_client.providers.get(namespace)

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
            decoded = jwt.decode(self.credentials['token']['access_token'], verify=False)
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
            return (ServicePrincipalCredentials(
                client_id=data['credentials']['client_id'],
                secret=data['credentials']['secret'],
                tenant=data['credentials']['tenant'],
                resource=self.resource_namespace
            ), data['subscription'])

    def get_functions_auth_string(self):
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

        function_subscription_id = self.get_function_target_subscription_id()

        # Use dedicated function env vars if available
        if all(k in os.environ for k in function_auth_variables):
            auth = {
                'credentials':
                    {
                        'client_id': os.environ[constants.ENV_FUNCTION_CLIENT_ID],
                        'secret': os.environ[constants.ENV_FUNCTION_CLIENT_SECRET],
                        'tenant': os.environ[constants.ENV_FUNCTION_TENANT_ID]
                    },
                'subscription': function_subscription_id
            }

        elif type(self.credentials) is ServicePrincipalCredentials:
            auth = {
                'credentials':
                    {
                        'client_id': os.environ[constants.ENV_CLIENT_ID],
                        'secret': os.environ[constants.ENV_CLIENT_SECRET],
                        'tenant': os.environ[constants.ENV_TENANT_ID]
                    },
                'subscription': function_subscription_id
            }

        else:
            raise NotImplementedError(
                "Service Principal credentials are the only "
                "supported auth mechanism for deploying functions.")

        return json.dumps(auth, indent=2)
