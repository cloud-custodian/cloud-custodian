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

from azure_common import BaseTest
from c7n_azure.session import Session
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.template_utils import TemplateUtilities

CONST_GROUP_NAME = 'cloud-custodian-test'


class FunctionAppUtilsTest(BaseTest):
    @classmethod
    def setUpClass(cls):
        super(FunctionAppUtilsTest, cls).setUpClass()
        template_util = TemplateUtilities()

        template_util.create_resource_group(CONST_GROUP_NAME, {'location': 'West US 2'})

        template_file = 'dedicated_functionapp.json'
        parameters = template_util.get_default_parameters(
            'dedicated_functionapp.test.parameters.json')
        template_util.deploy_resource_template(CONST_GROUP_NAME, template_file,
                                               parameters).wait()

    @classmethod
    def tearDownClass(cls):
        super(FunctionAppUtilsTest, cls).tearDownClass()
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        client.resource_groups.delete(CONST_GROUP_NAME)

    def setUp(self):
        super(FunctionAppUtilsTest, self).setUp()
        self.functionapp_util = FunctionAppUtilities()

    def test_get_storage_connection_string(self):
        template_util = TemplateUtilities()
        parameters = template_util.get_default_parameters(
            'dedicated_functionapp.test.parameters.json')

        storage_name = parameters['storageName']['value']
        conn_string = self.functionapp_util.get_storage_connection_string(
            CONST_GROUP_NAME, storage_name)

        self.assertIn('AccountName=%s;' % storage_name, conn_string)

    def test_get_application_insights_key_exists(self):
        template_util = TemplateUtilities()
        parameters = template_util.get_default_parameters(
            'dedicated_functionapp.test.parameters.json')

        app_insights_name = parameters['servicePlanName']['value']
        key = self.functionapp_util.get_application_insights_key(
            CONST_GROUP_NAME, app_insights_name)

        self.assertIsNotNone(key)

    def test_get_application_insights_key_not_exists(self):
        app_insights_name = 'does-not-exist'
        key = self.functionapp_util.get_application_insights_key(
            CONST_GROUP_NAME, app_insights_name)

        self.assertFalse(key)

    def test_deploy_webapp(self):
        s = Session()
        web_client = s.client('azure.mgmt.web.WebSiteManagementClient')

        template_util = TemplateUtilities()
        parameters = template_util.get_default_parameters(
            'dedicated_functionapp.test.parameters.json')

        service_plan = web_client.app_service_plans.get(
            CONST_GROUP_NAME, parameters['servicePlanName']['value'])
        self.assertIsNotNone(service_plan)
        webapp_name = 'test-deploy-webapp'
        self.functionapp_util.deploy_webapp(webapp_name,
                                            CONST_GROUP_NAME,
                                            service_plan,
                                            parameters['storageName']['value'])

        wep_app = web_client.web_apps.get(CONST_GROUP_NAME, webapp_name)
        self.assertIsNotNone(wep_app)
