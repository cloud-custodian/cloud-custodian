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
from c7n_azure.azure_events import AzureEvents
from c7n_azure.constants import CONST_AZURE_EVENT_TRIGGER_MODE
from c7n_azure.policy import AzureEventGridMode, AzureFunctionMode


class AzurePolicyModeTest(BaseTest):
    def setUp(self):
        super(AzurePolicyModeTest, self).setUp()

    def test_init_azure_function_mode_with_service_plan(self):
        p = self.load_policy({
            'name': 'test-azure-serverless-mode',
            'resource': 'azure.vm',
            'mode':
                {'type': CONST_AZURE_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite'],
                 'provision-options': {
                     'servicePlan': {
                         'name': 'test-cloud-custodian',
                         'location': 'eastus',
                         'resourceGroupName': 'test'}
                 }}
        })

        function_mode = AzureFunctionMode(p)
        self.assertEqual(function_mode.policy_name, p.data['name'])

        self.assertEqual(function_mode.storage_account['name'], 'cloudcustodian')
        self.assertEqual(function_mode.app_insights['name'], 'test-cloud-custodian')
        self.assertEqual(function_mode.service_plan['name'], "test-cloud-custodian")

        self.assertEqual(function_mode.service_plan['location'], "eastus")
        self.assertEqual(function_mode.app_insights['location'], "eastus")
        self.assertEqual(function_mode.storage_account['location'], "eastus")

        self.assertEqual(function_mode.storage_account['resource_group_name'], 'test')
        self.assertEqual(function_mode.app_insights['resource_group_name'], 'test')
        self.assertEqual(function_mode.service_plan['resource_group_name'], "test")

        self.assertEqual(function_mode.functionapp_name,
                         function_mode.service_plan['name'] + '-' + function_mode.policy_name)

    def test_init_azure_function_mode_no_service_plan_name(self):
        p = self.load_policy({
            'name': 'test-azure-serverless-mode',
            'resource': 'azure.vm',
            'mode':
                {'type': CONST_AZURE_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']}
        })

        function_mode = AzureFunctionMode(p)
        self.assertEqual(function_mode.policy_name, p.data['name'])

        self.assertEqual(function_mode.service_plan['name'], "cloud-custodian")
        self.assertEqual(function_mode.service_plan['location'], "westus2")
        self.assertEqual(function_mode.service_plan['resource_group_name'], "cloud-custodian")

        self.assertEqual(function_mode.app_insights['name'], 'cloud-custodian')
        self.assertEqual(function_mode.app_insights['location'], "westus2")
        self.assertEqual(function_mode.app_insights['resource_group_name'], 'cloud-custodian')

        self.assertEqual(function_mode.storage_account['name'], 'cloudcustodian')
        self.assertEqual(function_mode.storage_account['location'], "westus2")
        self.assertEqual(function_mode.storage_account['resource_group_name'], 'cloud-custodian')

        self.assertEqual(function_mode.functionapp_name,
                         function_mode.service_plan['name'] + '-' + function_mode.policy_name)

    def test_init_azure_function_mode_with_resource_ids(self):

        ai_id = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups' \
                '/testrg/providers/microsoft.insights/components/testai'
        sp_id = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups' \
                '/testrg/providers/Microsoft.Web/serverFarms/testsp'
        sa_id = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups' \
                '/testrg/providers/Microsoft.Storage/storageAccounts/testsa'
        p = self.load_policy({
            'name': 'test-azure-serverless-mode',
            'resource': 'azure.vm',
            'mode':
                {'type': CONST_AZURE_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite'],
                 'provision-options': {
                     'servicePlan': sp_id,
                     'storageAccount': sa_id,
                     'appInsights': ai_id
                 }}
        })

        function_mode = AzureFunctionMode(p)
        self.assertEqual(function_mode.policy_name, p.data['name'])

        self.assertEqual(function_mode.storage_account['id'], sa_id)
        self.assertEqual(function_mode.storage_account['name'], 'testsa')
        self.assertEqual(function_mode.storage_account['resource_group_name'], 'testrg')

        self.assertEqual(function_mode.app_insights['id'], ai_id)
        self.assertEqual(function_mode.app_insights['name'], 'testai')
        self.assertEqual(function_mode.app_insights['resource_group_name'], 'testrg')

        self.assertEqual(function_mode.service_plan['id'], sp_id)
        self.assertEqual(function_mode.service_plan['name'], "testsp")
        self.assertEqual(function_mode.service_plan['resource_group_name'], "testrg")

        self.assertEqual(function_mode.functionapp_name,
                         function_mode.service_plan['name'] + '-' + function_mode.policy_name)

    def test_event_mode_is_subscribed_to_event_true(self):
        p = self.load_policy({
            'name': 'test-azure-event',
            'resource': 'azure.vm',
            'mode':
                {'type': CONST_AZURE_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']},
        })

        subscribed_events = AzureEvents.get_event_operations(p.data['mode']['events'])
        event = {
            'data': {
                'operationName': 'Microsoft.Compute/virtualMachines/write'
            }
        }

        event_mode = AzureEventGridMode(p)
        self.assertTrue(event_mode._is_subscribed_to_event(event, subscribed_events))

    def test_event_mode_is_subscribed_to_event_false(self):
        p = self.load_policy({
            'name': 'test-azure-event',
            'resource': 'azure.vm',
            'mode':
                {'type': CONST_AZURE_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']},
        })

        subscribed_events = AzureEvents.get_event_operations(p.data['mode']['events'])
        event = {
            'data': {
                'operationName': 'Microsoft.Compute/virtualMachineScaleSets/write'
            }
        }
        event_mode = AzureEventGridMode(p)
        self.assertFalse(event_mode._is_subscribed_to_event(event, subscribed_events))
