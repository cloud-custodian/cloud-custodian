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

import json
import os
import re
from unittest.mock import patch

from azure.common.credentials import ServicePrincipalCredentials, BasicTokenAuthentication
from azure_common import BaseTest
from c7n_azure.session import Session


class SessionTest(BaseTest):
    def setUp(self):
        super(SessionTest, self).setUp()

    def mock_init(self, client_id, secret, tenant, resource):
        pass

    def test_initialize_session_principal(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__', autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                'AZURE_TENANT_ID': 'tenant',
                                'AZURE_SUBSCRIPTION_ID': 'ea42f556-5106-4743-99b0-c129bfa71a47',
                                'AZURE_CLIENT_ID': 'client',
                                'AZURE_CLIENT_SECRET': 'secret'
                            }, clear=True):

                s = Session()
                s._initialize_session()
                self.assertIs(type(s.credentials), ServicePrincipalCredentials)
                self.assertEqual(s.subscription_id, 'ea42f556-5106-4743-99b0-c129bfa71a47')

    def test_initialize_session_token(self):
        with patch.dict(os.environ,
                        {
                            'AZURE_ACCESS_TOKEN': 'token',
                            'AZURE_SUBSCRIPTION_ID': 'ea42f556-5106-4743-99b0-c129bfa71a47'
                        }, clear=True):
            s = Session()
            s._initialize_session()
            self.assertIs(type(s.credentials), BasicTokenAuthentication)
            self.assertEqual(s.subscription_id, 'ea42f556-5106-4743-99b0-c129bfa71a47')

    def test_get_functions_auth_string(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__', autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                'AZURE_TENANT_ID': 'tenant',
                                'AZURE_SUBSCRIPTION_ID': 'ea42f556-5106-4743-99b0-c129bfa71a47',
                                'AZURE_CLIENT_ID': 'client',
                                'AZURE_CLIENT_SECRET': 'secret'
                            }, clear=True):

                s = Session()
                s._initialize_session()
                auth = s.get_functions_auth_string()

                expected = """{
                              "credentials": {
                                "client_id": "client",
                                "secret": "secret",
                                "tenant": "tenant"
                              },
                              "subscription": "ea42f556-5106-4743-99b0-c129bfa71a47"
                            }"""

                self.assertEqual(json.loads(auth), json.loads(expected))

    def test_get_functions_auth_string_overrides(self):
        with patch('azure.common.credentials.ServicePrincipalCredentials.__init__', autospec=True, return_value=None):
            with patch.dict(os.environ,
                            {
                                'AZURE_TENANT_ID': 'tenant',
                                'AZURE_SUBSCRIPTION_ID': 'ea42f556-5106-4743-99b0-c129bfa71a47',
                                'AZURE_CLIENT_ID': 'client',
                                'AZURE_CLIENT_SECRET': 'secret',
                                'AZURE_FUNCTION_TENANT_ID': 'functiontenant',
                                'AZURE_FUNCTION_SUBSCRIPTION_ID': '000000-5106-4743-99b0-c129bfa71a47',
                                'AZURE_FUNCTION_CLIENT_ID': 'functionclient',
                                'AZURE_FUNCTION_CLIENT_SECRET': 'functionsecret'
                            }, clear=True):

                s = Session()
                s._initialize_session()
                auth = s.get_functions_auth_string()

                expected = """{
                              "credentials": {
                                "client_id": "functionclient",
                                "secret": "functionsecret",
                                "tenant": "functiontenant"
                              },
                              "subscription": "000000-5106-4743-99b0-c129bfa71a47"
                            }"""

                self.assertEqual(json.loads(auth), json.loads(expected))

    def test_api_version(self):
        """Verify we retrieve the correct API version for a resource type"""
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        resource = next(client.resources.list())
        self.assertTrue(re.match('\\d{4}-\\d{2}-\\d{2}',
                                 s.resource_api_version(resource.id)) is not None)
