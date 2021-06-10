# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from azure.core.exceptions import AzureError
from c7n.utils import local_session
from c7n_azure import constants
from c7n_azure.constants import FUNCTION_DOCKER_VERSION
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.provisioning.app_insights import AppInsightsUnit
from c7n_azure.provisioning.app_service_plan import AppServicePlanUnit
from c7n_azure.provisioning.function_app import FunctionAppDeploymentUnit
from c7n_azure.provisioning.storage_account import StorageAccountUnit
from c7n_azure.session import Session

from .azure_common import BaseTest, requires_arm_polling


@requires_arm_polling
# Due to the COVID-19 Azure hardened quota limits for internal subscriptions and some of the
# tests in this module might fail.
# It is not required during nightly live tests because we have e2e Azure Functions tests.
# They test same scenario.
@pytest.mark.skiplive
class DeploymentUnitsTest(BaseTest):

    rg_name = 'cloud-custodian-test-deployment-units'
    rg_location = 'westus'

    @classmethod
    def setUpClass(cls):
        super(DeploymentUnitsTest, cls).setUpClass()
        try:
            cls.session = local_session(Session)
            client = cls.session.client('azure.mgmt.resource.ResourceManagementClient')
            client.resource_groups.create_or_update(cls.rg_name, {'location': cls.rg_location})
        except AzureError:
            pass

    @classmethod
    def tearDownClass(cls):
        super(DeploymentUnitsTest, cls).tearDownClass()
        try:
            client = cls.session.client('azure.mgmt.resource.ResourceManagementClient')
            client.resource_groups.begin_delete(cls.rg_name)
        except AzureError:
            pass

    def _validate(self, unit, params):
        result = unit.provision(params)
        self.assertNotEqual(result, None)
        return result

    def test_app_insights(self):
        params = {'name': 'cloud-custodian-test',
                  'location': 'westus2',
                  'resource_group_name': self.rg_name}
        unit = AppInsightsUnit()

        self._validate(unit, params)

    def test_storage_account(self):
        params = {'name': 'custodianaccount47182745',
                  'location': self.rg_location,
                  'resource_group_name': self.rg_name}
        unit = StorageAccountUnit()

        self._validate(unit, params)

    def test_service_plan(self):
        params = {'name': 'cloud-custodian-test',
                  'location': self.rg_location,
                  'resource_group_name': self.rg_name,
                  'sku_tier': 'Basic',
                  'sku_name': 'B1'}
        unit = AppServicePlanUnit()

        self._validate(unit, params)

    def test_app_service_plan_autoscale(self):
        params = {'name': 'cloud-custodian-test-autoscale',
                  'location': self.rg_location,
                  'resource_group_name': self.rg_name,
                  'sku_tier': 'Basic',
                  'sku_name': 'B1',
                  'auto_scale': {
                      'enabled': True,
                      'min_capacity': 1,
                      'max_capacity': 2,
                      'default_capacity': 1}
                  }

        unit = AppServicePlanUnit()

        plan = self._validate(unit, params)
        client = self.session.client('azure.mgmt.monitor.MonitorManagementClient')
        rules = client.autoscale_settings.get(self.rg_name, constants.FUNCTION_AUTOSCALE_NAME)

        self.assertEqual(rules.target_resource_uri, plan.id)

    def test_function_app_consumption(self):
        # provision storage account
        sa_params = {
            'name': 'custodianaccount47182748',
            'location': self.rg_location,
            'resource_group_name': self.rg_name}
        storage_unit = StorageAccountUnit()
        storage_account_id = storage_unit.provision(sa_params).id
        conn_string = FunctionAppUtilities.get_storage_account_connection_string(storage_account_id)

        # provision function app
        func_params = {
            'name': 'cc-consumption-47182748',
            # Using different location due to http://go.microsoft.com/fwlink/?LinkId=825764
            'location': 'eastus2',
            'resource_group_name': self.rg_name,
            'app_service_plan_id': None,  # auto-provision a dynamic app plan
            'app_insights_key': None,
            'is_consumption_plan': True,
            'storage_account_connection_string': conn_string
        }
        func_unit = FunctionAppDeploymentUnit()
        func_app = self._validate(func_unit, func_params)

        # verify settings are properly configured
        self.assertEqual(func_app.kind, 'functionapp,linux')
        self.assertTrue(func_app.reserved)

    def test_function_app_dedicated(self):
        # provision storage account
        sa_params = {
            'name': 'custodianaccount47182741',
            'location': self.rg_location,
            'resource_group_name': self.rg_name}
        storage_unit = StorageAccountUnit()
        storage_account_id = storage_unit.provision(sa_params).id
        conn_string = FunctionAppUtilities.get_storage_account_connection_string(storage_account_id)

        # provision app plan
        app_plan_params = {
            'name': 'cloud-custodian-test2',
            'location': self.rg_location,
            'resource_group_name': self.rg_name,
            'sku_tier': 'Basic',
            'sku_name': 'B1'}
        app_plan_unit = AppServicePlanUnit()
        app_plan = app_plan_unit.provision(app_plan_params)

        # provision function app
        func_app_name = 'cc-dedicated-47182748'
        func_params = {
            'name': func_app_name,
            'location': self.rg_location,
            'resource_group_name': self.rg_name,
            'app_service_plan_id': app_plan.id,
            'app_insights_key': None,
            'is_consumption_plan': False,
            'storage_account_connection_string': conn_string
        }
        func_unit = FunctionAppDeploymentUnit()
        func_app = self._validate(func_unit, func_params)

        # verify settings are properly configured
        self.assertEqual(func_app.kind, 'functionapp,linux,container')
        self.assertTrue(func_app.reserved)

        wc = self.session.client('azure.mgmt.web.WebSiteManagementClient')

        site_config = wc.web_apps.get_configuration(self.rg_name, func_app_name)
        self.assertTrue(site_config.always_on)
        self.assertEqual(site_config.linux_fx_version, FUNCTION_DOCKER_VERSION)
