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

    def test_init_azure_function_mode_with_service_plan_name(self):
        p = self.load_policy({
            'name': 'test-azure-serverless-mode',
            'resource': 'azure.vm',
            'mode':
                {'type': CONST_AZURE_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite'],
                 'provision-options': {
                     'servicePlanName': 'test-cloud-custodian'
                 }}
        })

        function_mode = AzureFunctionMode(p)
        self.assertEqual(function_mode.policy_name, p.data['name'])
        self.assertEqual(function_mode.webapp_name, function_mode.parameters['name']['value'])
        self.assertEqual(function_mode.parameters['storageName']['value'], 'testcloudcustodian')
        self.assertEqual(function_mode.group_name,
                         p.data['mode']['provision-options']['servicePlanName'])

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
        self.assertEqual(function_mode.webapp_name, function_mode.parameters['name']['value'])
        self.assertEqual(function_mode.group_name,
                         function_mode.parameters['servicePlanName']['value'])
        self.assertEqual(function_mode.parameters['servicePlanName']['value'], 'cloud-custodian')

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
