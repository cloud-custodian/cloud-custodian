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

from msrestazure.azure_exceptions import CloudError

from c7n.utils import local_session
from c7n_azure.session import Session

from c7n_azure.provisioning.app_insights import AppInsightsUnit
from c7n_azure.provisioning.storage_account import StorageAccountUnit
from c7n_azure.provisioning.app_service_plan import AppServicePlanUnit


class DeploymentUnitsTest(BaseTest):

    rg_name = 'custodian-test-deployment-units'

    @classmethod
    def tearDownClass(cls):
        try:
            client = local_session(Session).client('azure.mgmt.resource.ResourceManagementClient')
            client.resource_groups.delete(cls.rg_name)
        except CloudError:
            pass

    def _validate(self, unit, params):
        self.assertEqual(unit.get(params), None)
        result = unit.provision_if_not_exists(params)
        self.assertNotEqual(result, None)

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
