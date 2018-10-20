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

from c7n_azure.provisioning.app_insights import AppInsightsUnit

from c7n.utils import local_session
from c7n_azure.session import Session

CONST_GROUP_NAME = 'test_functionapp-reqs'


class FunctionAppUtilsTest(BaseTest):
    def setUp(self):
        super(FunctionAppUtilsTest, self).setUp()
        self.functionapp_util = FunctionAppUtilities()

    @arm_template('functionapp-reqs.json')
    def test_get_storage_connection_string(self):
        storage_name = 'cloudcustodiantest'
        id = '/subscriptions/%s/resourceGroups/test_functionapp-reqs/providers/Microsoft.Storage' \
             '/storageAccounts/cloudcustodiantest' % local_session(Session).subscription_id
        conn_string = FunctionAppUtilities.get_storage_account_connection_string(id)
        self.assertIn('AccountName=%s;' % storage_name, conn_string)

    @arm_template('functionapp-reqs.json')
    def test_get_application_insights_key_exists(self):
        insights = AppInsightsUnit().get({'name': 'cloud-custodian-test',
                                          'resource_group_name': CONST_GROUP_NAME})

        self.assertIsNotNone(insights)
        self.assertIsNotNone(insights.instrumentation_key)

    @arm_template('functionapp-reqs.json')
    def test_deploy_function_app(self):

        parameters = FunctionAppUtilities.FunctionAppInfrastructureParameters(
            app_insights={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test'
            },
            storage_account={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloudcustodiantest'
            },
            service_plan={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test'
            },
            functionapp_name='custodian-test-app')

        app = self.functionapp_util.deploy_dedicated_function_app(parameters)
        self.assertIsNotNone(app)
