# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest, arm_template
from c7n_azure.function_package import FunctionPackage, AzurePythonPackageArchive
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
        self.subscription_id = self.session.get_subscription_id()
        self.storage_name = 'ccfuncapp%s' % self.subscription_id[-12:]
        self.dedicated_function_name = 'cloud-custodian-test-dedicated%s' \
            % self.subscription_id[-12:]

    @arm_template('functionapp-reqs.json')
    def test_get_storage_connection_string(self):
        id = '/subscriptions/%s/resourceGroups/test_functionapp-reqs/providers/Microsoft.Storage' \
             '/storageAccounts/%s' % (self.subscription_id, self.storage_name)
        conn_string = FunctionAppUtilities.get_storage_account_connection_string(id)
        self.assertIn('AccountName=%s;' % self.storage_name, conn_string)

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
                'name': self.storage_name
            },
            service_plan={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test',
                'location': 'westus2'
            },
            function_app={'resource_group_name': CONST_GROUP_NAME,
                          'name': 'custodian-test-app'})

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
                'name': self.storage_name
            },
            service_plan={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test',
                'sku_tier': 'something wrong'
            },
            function_app={
                'name': self.dedicated_function_name,
                'resource_group_name': CONST_GROUP_NAME})

        FunctionAppUtilities.deploy_function_app(parameters)
        self.assertEqual(parameters.service_plan['sku_tier'], 'Basic')

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
            function_app={
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test'})

        self.assertTrue(FunctionAppUtilities.is_consumption_plan(params))

        params.service_plan['sku_tier'] = 'other'
        self.assertFalse(FunctionAppUtilities.is_consumption_plan(params))

    @arm_template('functionapp-reqs.json')
    @patch('time.sleep')
    def test_publish_functions_package_consumption(self, _1):
        function_app_name = 'cloud-custodian-test-consumption%s' % self.subscription_id[-12:]
        parameters = FunctionAppUtilities.FunctionAppInfrastructureParameters(
            app_insights={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test'
            },
            storage_account={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': self.storage_name
            },
            service_plan={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test',
                'sku_tier': 'dynamic'
            },
            function_app={'resource_group_name': CONST_GROUP_NAME,
                          'name': function_app_name})

        package = FunctionPackage("TestPolicy")
        package.pkg = AzurePythonPackageArchive()
        package.close()

        FunctionAppUtilities.publish_functions_package(
            parameters, package)

        # verify app setting updated
        wc = self.session.client('azure.mgmt.web.WebSiteManagementClient')
        app_settings = wc.web_apps.list_application_settings(
            CONST_GROUP_NAME, function_app_name)
        self.assertNotIn('WEBSITE_RUN_FROM_PACKAGE', app_settings.properties)

    @arm_template('functionapp-reqs.json')
    @patch('time.sleep')
    def test_publish_functions_package_dedicated(self, _1):
        parameters = FunctionAppUtilities.FunctionAppInfrastructureParameters(
            app_insights={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test'
            },
            storage_account={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': self.storage_name
            },
            service_plan={
                'id': '',
                'resource_group_name': CONST_GROUP_NAME,
                'name': 'cloud-custodian-test',
                'sku_tier': 'Basic'
            },
            function_app={
                'resource_group_name': CONST_GROUP_NAME,
                'name': self.dedicated_function_name})

        package = FunctionPackage("TestPolicy")
        package.pkg = AzurePythonPackageArchive()
        package.close()

        FunctionAppUtilities.publish_functions_package(parameters, package)
