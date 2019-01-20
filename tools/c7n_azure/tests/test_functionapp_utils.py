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
from c7n_azure.function_package import FunctionPackage
from c7n_azure.functionapp_utils import FunctionAppUtilities

from c7n_azure.provisioning.app_insights import AppInsightsUnit
from mock import patch

from c7n.utils import local_session
from c7n_azure.session import Session

CONST_GROUP_NAME = 'test_functionapp-reqs'
prefix = 'hxxuvke6yrmoe'


class FunctionAppUtilsTest(BaseTest):
    def setUp(self):
        super(FunctionAppUtilsTest, self).setUp()
        self.session = local_session(Session)

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
            function_app_resource_group_name=CONST_GROUP_NAME,
            function_app_name='custodian-test-app')

        app = FunctionAppUtilities.deploy_function_app(parameters)
        self.assertIsNotNone(app)

    @arm_template('functionapp-reqs.json')
    def test_deploy_function_app_pre_existing_app_fetch_actual_sku_tier(self):

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
                'name': 'cloud-custodian-test',
                'sku_tier': 'something wrong'
            },
            function_app_resource_group_name=CONST_GROUP_NAME,
            function_app_name='cloud-custodian-test')

        FunctionAppUtilities.deploy_function_app(parameters)
        self.assertEquals(parameters.service_plan['sku_tier'], 'Basic')

    def test_get_function_name_replacements(self):
        test_cases = [
            ('test-function-name', 'test-function-name-suffix'),
            ('test_function_name', 'test-function-name-suffix'),
            ('test-function-name123', 'test-function-name123-suffix'),
            ('test-function-name!@#$', 'test-function-name-----suffix')
        ]

        for test_case in test_cases:
            self.assertEqual(test_case[1], FunctionAppUtilities.get_function_name(
                policy_name=test_case[0], suffix='suffix'))

    def test_validate_function_name_length_requirements(self):
        with self.assertRaises(ValueError):
            FunctionAppUtilities.validate_function_name(function_name=None)
        with self.assertRaises(ValueError):
            FunctionAppUtilities.validate_function_name(function_name='')
        with self.assertRaises(ValueError):
            FunctionAppUtilities.validate_function_name(
                function_name='abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmn')

    def test_is_consumption_plan(self):
        params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
            app_insights=None,
            storage_account=None,
            service_plan={
                'sku_tier': 'dynamic'
            },
            function_app_resource_group_name=CONST_GROUP_NAME,
            function_app_name='cloud-custodian-test')

        self.assertTrue(FunctionAppUtilities.is_consumption_plan(params))

        params.service_plan['sku_tier'] = 'other'
        self.assertFalse(FunctionAppUtilities.is_consumption_plan(params))

    @arm_template('functionapp-reqs.json')
    def test_publish_functions_package_consumption(self):
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
                'name': 'cloud-custodian-test',
                'sku_tier': 'dynamic'
            },
            function_app_resource_group_name=CONST_GROUP_NAME,
            function_app_name='cloud-custodian-test')

        FunctionAppUtilities.publish_functions_package(
            parameters, FunctionPackage("TestPolicy"))

        # verify app setting updated
        wc = self.session.client('azure.mgmt.web.WebSiteManagementClient')
        app_settings = wc.web_apps.list_application_settings(
            CONST_GROUP_NAME, 'cloud-custodian-test')
        self.assertIsNotNone(app_settings.properties['WEBSITE_RUN_FROM_PACKAGE'])

    @arm_template('functionapp-reqs.json')
    @patch('c7n_azure.function_package.FunctionPackage.publish')
    def test_publish_functions_package_dedicated(self, mock_function_package_publish):
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
                'name': 'cloud-custodian-test',
                'sku_tier': 'Basic'
            },
            function_app_resource_group_name=CONST_GROUP_NAME,
            function_app_name='cloud-custodian-test')

        FunctionAppUtilities.publish_functions_package(parameters, FunctionPackage("TestPolicy"))
        mock_function_package_publish.assert_called_once()
