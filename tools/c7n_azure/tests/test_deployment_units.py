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
from c7n_azure.constants import FUNCTION_DOCKER_VERSION
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.provisioning.app_insights import AppInsightsUnit
from c7n_azure.provisioning.app_service_plan import AppServicePlanUnit
from c7n_azure.provisioning.function_app import FunctionAppDeploymentUnit
from c7n_azure.provisioning.storage_account import StorageAccountUnit
from c7n_azure.session import Session
from msrestazure.azure_exceptions import CloudError

from c7n.utils import local_session


class DeploymentUnitsTest(BaseTest):

    rg_name = 'custodian-test-deployment-units'

    @classmethod
    def setUpClass(cls):
        cls.session = local_session(Session)

    @classmethod
    def tearDownClass(cls):
        try:
            client = cls.session.client('azure.mgmt.resource.ResourceManagementClient')
            client.resource_groups.delete(cls.rg_name)
        except CloudError:
            pass

    def _validate(self, unit, params):
        self.assertEqual(unit.get(params), None)
        result = unit.provision_if_not_exists(params)
        self.assertNotEqual(result, None)
        return result

    def test_app_insights(self):
        params = {'name': 'cloud-custodian-test',
                  'location': 'westus2',
                  'resource_group_name': self.rg_name}
        unit = AppInsightsUnit()

        self._validate(unit, params)

    def test_storage_account(self):
        params = {'name': 'custodianaccount47182748',
                  'location': 'westus2',
                  'resource_group_name': self.rg_name}
        unit = StorageAccountUnit()

        self._validate(unit, params)

    def test_service_plan(self):
        params = {'name': 'cloud-custodian-test',
                  'location': 'westus2',
                  'resource_group_name': self.rg_name,
                  'sku_tier': 'Basic',
                  'sku_name': 'B1'}
        unit = AppServicePlanUnit()

        self._validate(unit, params)

    def test_function_app_consumption(self):
        # provision storage account
        sa_params = {
            'name': 'custodianaccount47182748',
            'location': 'westus2',
            'resource_group_name': self.rg_name}
        storage_unit = StorageAccountUnit()
        storage_account_id = storage_unit.provision_if_not_exists(sa_params).id
        conn_string = FunctionAppUtilities.get_storage_account_connection_string(storage_account_id)

        # provision function app
        func_params = {
            'name': 'cc-consumption-47182748',
            'location': 'westus',
            'resource_group_name': self.rg_name,
            'app_service_plan_id': None,  # auto-provision a dynamic app plan
            'app_insights_key': None,
            'is_consumption_plan': True,
            'storage_account_connection_string': conn_string
        }
        func_unit = FunctionAppDeploymentUnit()
        func_app = self._validate(func_unit, func_params)

        # verify settings are properly configured
        self.assertEquals(func_app.kind, 'functionapp,linux')
        self.assertTrue(func_app.reserved)

    def test_function_app_dedicated(self):
        # provision storage account
        sa_params = {
            'name': 'custodianaccount47182748',
            'location': 'westus2',
            'resource_group_name': self.rg_name}
        storage_unit = StorageAccountUnit()
        storage_account_id = storage_unit.provision_if_not_exists(sa_params).id
        conn_string = FunctionAppUtilities.get_storage_account_connection_string(storage_account_id)

        # provision app plan
        app_plan_params = {
            'name': 'cloud-custodian-test',
            'location': 'westus2',
            'resource_group_name': self.rg_name,
            'sku_tier': 'Basic',
            'sku_name': 'B1'}
        app_plan_unit = AppServicePlanUnit()
        app_plan = app_plan_unit.provision_if_not_exists(app_plan_params)

        # provision function app
        func_app_name = 'cc-dedicated-47182748'
        func_params = {
            'name': func_app_name,
            'location': 'westus',
            'resource_group_name': self.rg_name,
            'app_service_plan_id': app_plan.id,
            'app_insights_key': None,
            'is_consumption_plan': False,
            'storage_account_connection_string': conn_string
        }
        func_unit = FunctionAppDeploymentUnit()
        func_app = self._validate(func_unit, func_params)

        # verify settings are properly configured
        self.assertEquals(func_app.kind, 'functionapp,linux,container')
        self.assertTrue(func_app.reserved)

        wc = self.session.client('azure.mgmt.web.WebSiteManagementClient')

        site_config = wc.web_apps.get_configuration(self.rg_name, func_app_name)
        self.assertTrue(site_config.always_on)
        self.assertEquals(site_config.linux_fx_version, FUNCTION_DOCKER_VERSION)

        app_settings = wc.web_apps.list_application_settings(self.rg_name, func_app_name)
        self.assertIsNotNone(app_settings.properties['MACHINEKEY_DecryptionKey'])
