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

from azure_common import BaseTest, arm_template
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.session import Session

CONST_GROUP_NAME = 'test_functionapp-reqs'


class FunctionAppUtilsTest(BaseTest):
    def setUp(self):
        super(FunctionAppUtilsTest, self).setUp()
        self.functionapp_util = FunctionAppUtilities()

    @arm_template('functionapp-reqs.json')
    def test_get_storage_connection_string(self):
        storage_name = 'cloudcustodiantest'
        conn_string = self.functionapp_util.get_storage_connection_string(
            CONST_GROUP_NAME, storage_name)

        self.assertIn('AccountName=%s;' % storage_name, conn_string)

    @arm_template('functionapp-reqs.json')
    def test_get_application_insights_key_exists(self):
        app_insights_name = 'cloud-custodian-test'
        key = self.functionapp_util.get_application_insights_key(
            CONST_GROUP_NAME, app_insights_name)

        self.assertIsNotNone(key)

    @arm_template('functionapp-reqs.json')
    def test_get_application_insights_key_not_exists(self):
        app_insights_name = 'does-not-exist'
        key = self.functionapp_util.get_application_insights_key(
            CONST_GROUP_NAME, app_insights_name)

        self.assertFalse(key)

    @arm_template('functionapp-reqs.json')
    def test_deploy_webapp(self):
        s = Session()
        web_client = s.client('azure.mgmt.web.WebSiteManagementClient')

        service_plan = web_client.app_service_plans.get(
            CONST_GROUP_NAME, 'cloud-custodian-test')
        self.assertIsNotNone(service_plan)
        webapp_name = 'test-deploy-webapp'
        self.functionapp_util.deploy_webapp(webapp_name,
                                            CONST_GROUP_NAME,
                                            service_plan,
                                            'cloudcustodiantest')

        wep_app = web_client.web_apps.get(CONST_GROUP_NAME, webapp_name)
        self.assertIsNotNone(wep_app)
