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

class TestFunctionAppUtils(BaseTest):
    def setUp(self):
        super(TestFunctionAppUtils, self).setUp()
        self.template_util = TemplateUtilities()
        self.functionapp_util = FunctionAppUtilities()

    def test_deploy_webapp(self):
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')

        self.template_util.create_resource_group(CONST_GROUP_NAME, {'location': 'West US 2'})
        resource_group = client.resource_groups.get(CONST_GROUP_NAME)

        self.assertIsNotNone(resource_group)

        template_file = 'dedicated_functionapp.json'
        parameters = self.template_util.get_default_parameters(
            'dedicated_functionapp.test.parameters.json')
        self.template_util.deploy_resource_template(CONST_GROUP_NAME, template_file,
                                                    parameters).wait()

        resources = client.resources.list_by_resource_group(CONST_GROUP_NAME)
        self.assertIsNotNone(resources)

        web_client = s.client('azure.mgmt.web.WebSiteManagementClient')
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
        client.resource_groups.delete(CONST_GROUP_NAME)
