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

from azure.mgmt.storage.models import StorageAccount
from azure_common import BaseTest, DEFAULT_SUBSCRIPTION_ID, arm_template, cassette_name
from c7n_azure.constants import FUNCTION_EVENT_TRIGGER_MODE, FUNCTION_TIME_TRIGGER_MODE, \
    CONTAINER_EVENT_TRIGGER_MODE, CONTAINER_TIME_TRIGGER_MODE
from c7n_azure.policy import AzureEventGridMode, AzureFunctionMode, AzureModeCommon
from jsonschema import ValidationError
from mock import mock, patch, Mock


class AzurePolicyModeTest(BaseTest):
    def setUp(self):
        super(AzurePolicyModeTest, self).setUp()

    def test_azure_function_event_mode_schema_validation(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-serverless-mode',
                'resource': 'azure.vm',
                'mode':
                    {'type': FUNCTION_EVENT_TRIGGER_MODE,
                     'events': ['VmWrite'],
                     'provision-options': {
                         'servicePlan': {
                             'name': 'test-cloud-custodian',
                             'location': 'eastus',
                             'resourceGroupName': 'test'},
                         'storageAccount': {
                             'name': 'testschemaname'
                         },
                         'appInsights': {
                             'name': 'testschemaname'
                         }
                     }}
            }, validate=True)
            self.assertTrue(p)

    def test_azure_function_event_mode_too_many_events_throws(self):
        with self.sign_out_patch():
            with self.assertRaises(ValidationError):
                self.load_policy({
                    'name': 'test-azure-serverless-mode',
                    'resource': 'azure.vm',
                    'mode': {
                        'type': FUNCTION_EVENT_TRIGGER_MODE,
                        'events': [
                            'VmWrite',
                            'AppServicePlanWrite',
                            'CognitiveServiceWrite',
                            'CosmosDbWrite',
                            'DataFactoryWrite',
                            'DataLakeWrite'
                        ]
                    }
                }, validate=True)

    def test_azure_function_periodic_mode_schema_validation(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-serverless-mode',
                'resource': 'azure.vm',
                'mode':
                    {'type': FUNCTION_TIME_TRIGGER_MODE,
                     'schedule': '0 */5 * * * *',
                     'provision-options': {
                         'servicePlan': {
                             'name': 'test-cloud-custodian',
                             'location': 'eastus',
                             'resourceGroupName': 'test'},
                         'storageAccount': {
                             'name': 'testschemaname'
                         },
                         'appInsights': {
                             'name': 'testschemaname'
                         }
                     }}
            }, validate=True)
            self.assertTrue(p)

    def test_azure_function_periodic_schema_schedule_valid(self):
        policy = {
            'name': 'test-azure-schema-schedule-valid',
            'resource': 'azure.vm',
            'mode': {
                'type': FUNCTION_TIME_TRIGGER_MODE,
                'schedule': ''
            }
        }

        valid_schedules = [
            '0 5 */2 * * friday',
            '0 * 5 * February *',
            '5-7 * * * * 1-5',
            '5,8,10 * * * Jan Mon'
        ]

        result = True
        for valid_schedule in valid_schedules:
            policy['mode']['schedule'] = valid_schedule
            p = self.load_policy(policy, validate=True)
            result = result and p

        self.assertTrue(result)

    def test_azure_function_periodic_schema_schedule_invalid(self):
        policy = {
            'name': 'test-azure-schema-schedule-invalid',
            'resource': 'azure.vm',
            'mode': {
                'type': FUNCTION_TIME_TRIGGER_MODE,
                'schedule': ''
            }
        }

        invalid_schedules = [
            '* * * * *',
            '0 * * * * * *',
            '* * * * * *',
            '0 0 0 0 0 0',
            '15-60 * * * * 7'
        ]

        for invalid_schedule in invalid_schedules:
            policy['mode']['schedule'] = invalid_schedule
            with self.assertRaises(ValidationError):
                self.load_policy(policy, validate=True)

    def test_container_periodic_schema_schedule_valid(self):
        policy = {
            'name': 'test-azure-periodic-mode',
            'resource': 'azure.vm',
            'mode':
                {'type': CONTAINER_TIME_TRIGGER_MODE,
                    'schedule': ''}
        }

        valid_schedules = [
            '5 */2 * * fri',
            ' * 5 * feb * ',
            '5-7 * * * 1-5 ',
            '5,8,10 * * jan mon'
        ]

        result = True
        for valid_schedule in valid_schedules:
            policy['mode']['schedule'] = valid_schedule
            p = self.load_policy(policy, validate=True)
            result = result and p

        self.assertTrue(result)

    def test_container_periodic_schema_schedule_invalid(self):
        policy = {
            'name': 'test-azure-periodic-mode',
            'resource': 'azure.vm',
            'mode':
                {'type': CONTAINER_TIME_TRIGGER_MODE,
                    'schedule': ''}
        }

        invalid_schedules = [
            '* * * *',
            '* * * * * *'
            '*/15 * Jan 1-5',
            '* 15 * jan 7',
        ]

        for invalid_schedule in invalid_schedules:
            policy['mode']['schedule'] = invalid_schedule
            with self.assertRaises(ValidationError):
                self.load_policy(policy, validate=True)

    def test_container_event_mode_schema_validation(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-event-mode',
                'resource': 'azure.vm',
                'mode':
                    {'type': CONTAINER_EVENT_TRIGGER_MODE,
                     'events': ['VmWrite']}
            }, validate=True)
            self.assertTrue(p)

    def test_container_periodic_mode_schema_validation(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-periodic-mode',
                'resource': 'azure.vm',
                'mode':
                    {'type': CONTAINER_TIME_TRIGGER_MODE,
                     'schedule': '*/5 * * * *'}
            }, validate=True)
            self.assertTrue(p)

    def test_init_azure_function_mode_with_service_plan(self):
        p = self.load_policy({
            'name': 'test-azure-serverless-mode',
            'resource': 'azure.vm',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite'],
                 'provision-options': {
                     'servicePlan': {
                         'name': 'test-cloud-custodian',
                         'location': 'eastus',
                         'resourceGroupName': 'test'}
                 }}
        })

        function_mode = AzureFunctionMode(p)
        params = function_mode.get_function_app_params()

        self.assertEqual(function_mode.policy_name, p.data['name'])

        self.assertTrue(params.storage_account['name'].startswith('custodian'))
        self.assertEqual(params.app_insights['name'], 'test-cloud-custodian')
        self.assertEqual(params.service_plan['name'], "test-cloud-custodian")

        self.assertEqual(params.service_plan['location'], "eastus")
        self.assertEqual(params.app_insights['location'], "eastus")
        self.assertEqual(params.storage_account['location'], "eastus")

        self.assertEqual(params.storage_account['resource_group_name'], 'test')
        self.assertEqual(params.app_insights['resource_group_name'], 'test')
        self.assertEqual(params.service_plan['resource_group_name'], "test")

        self.assertTrue(params.function_app_name.startswith('test-azure-serverless-mode-'))

    def test_init_azure_function_mode_no_service_plan_name(self):
        p = self.load_policy({
            'name': 'test-azure-serverless-mode',
            'resource': 'azure.vm',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']}
        })

        function_mode = AzureFunctionMode(p)
        params = function_mode.get_function_app_params()

        self.assertEqual(function_mode.policy_name, p.data['name'])

        self.assertEqual(params.service_plan['name'], "cloud-custodian")
        self.assertEqual(params.service_plan['location'], "eastus")
        self.assertEqual(params.service_plan['resource_group_name'], "cloud-custodian")

        self.assertEqual(params.app_insights['name'], 'cloud-custodian')
        self.assertEqual(params.app_insights['location'], "eastus")
        self.assertEqual(params.app_insights['resource_group_name'], 'cloud-custodian')

        self.assertTrue(params.storage_account['name'].startswith('custodian'))
        self.assertEqual(params.storage_account['location'], "eastus")
        self.assertEqual(params.storage_account['resource_group_name'], 'cloud-custodian')

        self.assertTrue(params.function_app_name.startswith('test-azure-serverless-mode-'))

    def test_init_azure_function_mode_invalid_policy_name(self):
        p = self.load_policy({
            'name': 'this-policy-name-is-going-to-be-too-long-since-the-maximum-size-is-60',
            'resource': 'azure.vm',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']}
        })

        function_mode = AzureFunctionMode(p)
        with self.assertRaises(ValueError):
            function_mode.get_function_app_params()

    def test_init_azure_function_mode_invalid_characters_in_policy_name(self):
        p = self.load_policy({
            'name': 'invalid_policy_name1',
            'resource': 'azure.vm',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']}
        })

        function_mode = AzureFunctionMode(p)
        params = function_mode.get_function_app_params()
        self.assertRegex(params.function_app_name, "invalid-policy-name1-[a-zA-Z0-9]+")

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
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite'],
                 'provision-options': {
                     'servicePlan': sp_id,
                     'storageAccount': sa_id,
                     'appInsights': ai_id
                 }}
        })

        function_mode = AzureFunctionMode(p)
        params = function_mode.get_function_app_params()

        self.assertEqual(function_mode.policy_name, p.data['name'])

        self.assertEqual(params.storage_account['id'], sa_id)
        self.assertEqual(params.storage_account['name'], 'testsa')
        self.assertEqual(params.storage_account['resource_group_name'], 'testrg')

        self.assertEqual(params.app_insights['id'], ai_id)
        self.assertEqual(params.app_insights['name'], 'testai')
        self.assertEqual(params.app_insights['resource_group_name'], 'testrg')

        self.assertEqual(params.service_plan['id'], sp_id)
        self.assertEqual(params.service_plan['name'], "testsp")
        self.assertEqual(params.service_plan['resource_group_name'], "testrg")

        self.assertTrue(params.function_app_name.startswith('test-azure-serverless-mode-'))

    def test_event_grid_mode_creates_advanced_filtered_subscription(self):
        p = self.load_policy({
            'name': 'test-azure-event',
            'resource': 'azure.vm',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['VmWrite']},
        })

        with mock.patch('c7n_azure.azure_events.AzureEventSubscription.create') as mock_create:
            storage_account = StorageAccount(id=1, location='westus')
            event_mode = AzureEventGridMode(p)
            event_mode.target_subscription_ids = [DEFAULT_SUBSCRIPTION_ID]
            event_mode._create_event_subscription(storage_account, 'some_queue', None)

            name, args, kwargs = mock_create.mock_calls[0]

            # verify the advanced filter created
            event_filter = args[4].advanced_filters[0]
            self.assertEqual(event_filter.key, 'Data.OperationName')
            self.assertEqual(event_filter.values, ['Microsoft.Compute/virtualMachines/write'])
            self.assertEqual(event_filter.operator_type, 'StringIn')

    def test_event_grid_mode_creates_advanced_filtered_subscription_with_multiple_events(self):
        p = self.load_policy({
            'name': 'test-azure-event',
            'resource': 'azure.vm',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events':
                     ['VmWrite',
                        {
                            'resourceProvider': 'Microsoft.Resources/subscriptions/resourceGroups',
                            'event': 'write'
                        }]},
        })

        with mock.patch('c7n_azure.azure_events.AzureEventSubscription.create') as mock_create:
            storage_account = StorageAccount(id=1, location='westus')
            event_mode = AzureEventGridMode(p)
            event_mode.target_subscription_ids = [DEFAULT_SUBSCRIPTION_ID]
            event_mode._create_event_subscription(storage_account, 'some_queue', None)

            name, args, kwargs = mock_create.mock_calls[0]

            # verify the advanced filter created
            event_filter = args[4].advanced_filters[0]
            self.assertEqual(event_filter.key, 'Data.OperationName')
            self.assertEqual(event_filter.values,
                             ['Microsoft.Compute/virtualMachines/write',
                              'Microsoft.Resources/subscriptions/resourceGroups/write'])
            self.assertEqual(event_filter.operator_type, 'StringIn')

    def test_extract_properties(self):
        resource_id = '/subscriptions/{0}/resourceGroups/rg/providers' \
                      '/Microsoft.Web/serverFarms/test'.format(DEFAULT_SUBSCRIPTION_ID)
        r = AzureFunctionMode.extract_properties({}, '', {})
        self.assertEqual(r, {})

        r = AzureFunctionMode.extract_properties({}, 'v', {'v': 'default'})
        self.assertEqual(r, {'v': 'default'})

        r = AzureFunctionMode.extract_properties({'v': resource_id}, 'v', {'v': 'default'})
        self.assertEqual(r, {'id': resource_id, 'name': 'test', 'resource_group_name': 'rg'})

        r = AzureFunctionMode.extract_properties(
            {'v': {'test1': 'value1', 'testCamel': 'valueCamel'}},
            'v',
            {'test1': None, 'test_camel': None})
        self.assertEqual(r, {'test1': 'value1', 'test_camel': 'valueCamel'})

        r = AzureFunctionMode.extract_properties(
            {'v': {'t1': 'v1', 'nestedValue': {'testCamel': 'valueCamel'}}},
            'v',
            {'t1': None, 'nested_value': {'test_camel': None}, 't2': 'v2'})
        self.assertEqual(r, {'t1': 'v1', 't2': 'v2', 'nested_value': {'test_camel': 'valueCamel'}})

    @arm_template('emptyrg.json')
    @cassette_name('resourcegroup')
    @patch('c7n_azure.actions.delete.DeleteAction._process_resource')
    def test_empty_group_function_event(self, mock_delete):
        p = self.load_policy({
            'name': 'test-azure-resource-group',
            'mode':
                {'type': FUNCTION_EVENT_TRIGGER_MODE,
                 'events': ['ResourceGroupWrite'],
                 'provision-options': {
                     'servicePlan': {
                         'name': 'test-cloud-custodian'
                     }
                 }},
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'test_emptyrg'},
                {'type': 'empty-group'}],
            'actions': [
                {'type': 'delete'}]})

        event = AzurePolicyModeTest.get_sample_event()

        resources = p.push(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test_emptyrg')
        self.assertTrue(mock_delete.called)

    @arm_template('emptyrg.json')
    @cassette_name('resourcegroup')
    @patch('c7n_azure.actions.delete.DeleteAction._process_resource')
    def test_empty_group_container_event(self, mock_delete):
        p = self.load_policy({
            'name': 'test-azure-resource-group',
            'mode':
                {'type': CONTAINER_EVENT_TRIGGER_MODE,
                 'events': ['ResourceGroupWrite']},
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'test_emptyrg'},
                {'type': 'empty-group'}],
            'actions': [
                {'type': 'delete'}]})

        event = AzurePolicyModeTest.get_sample_event()

        resources = p.push(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test_emptyrg')
        self.assertTrue(mock_delete.called)

    @arm_template('emptyrg.json')
    def test_empty_group_container_scheduled(self):
        p = self.load_policy({
            'name': 'test-azure-resource-group',
            'mode':
                {'type': CONTAINER_TIME_TRIGGER_MODE,
                 'schedule': '* * * * *'},
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'test_emptyrg'},
                {'type': 'empty-group'}]})

        resources = p.push(None, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test_emptyrg')

    def test_extract_resource_id(self):
        rg_id = "/subscriptions/ea98974b-5d2a-4d98-a78a-382f3715d07e/resourceGroups/test_emptyrg"
        nsg_id = rg_id + '/providers/Microsoft.Network/networkSecurityGroups/test-nsg'
        sr_id = nsg_id + '/securityRules/test-rule'
        string_as_is = 'as-is-for-armresource'
        resource_type = ''
        policy = Mock()
        policy.resource_manager.resource_type.resource_type = resource_type

        event = {'subject': rg_id}
        policy.resource_manager.resource_type.resource_type = \
            'resourceGroups'
        self.assertEqual(AzureModeCommon.extract_resource_id(policy, event), rg_id)

        event = {'subject': nsg_id}
        policy.resource_manager.resource_type.resource_type = \
            'resourceGroups'
        self.assertEqual(AzureModeCommon.extract_resource_id(policy, event), rg_id)

        event = {'subject': nsg_id}
        policy.resource_manager.resource_type.resource_type =\
            'Microsoft.Network/networksecuritygroups'
        self.assertEqual(AzureModeCommon.extract_resource_id(policy, event), nsg_id)

        event = {'subject': sr_id}
        policy.resource_manager.resource_type.resource_type =\
            'Microsoft.Network/networksecuritygroups'
        self.assertEqual(AzureModeCommon.extract_resource_id(policy, event), nsg_id)

        event = {'subject': string_as_is}
        policy.resource_manager.resource_type.resource_type =\
            'armresource'
        self.assertEqual(AzureModeCommon.extract_resource_id(policy, event), string_as_is)

    @staticmethod
    def get_sample_event():
        return {"subject": "/subscriptions/ea98974b-5d2a-4d98-a78a-382f3715d07e/"
                           "resourceGroups/test_emptyrg",
                "eventType": "Microsoft.Resources.ResourceWriteSuccess",
                "eventTime": "2019-07-16T18:30:43.3595255Z",
                "id": "619d2674-b396-4356-9619-6c5a52fe4e88",
                "data": {
                    "correlationId": "7dd5a476-e052-40e2-99e4-bb9852dc1f86",
                    "resourceProvider": "Microsoft.Resources",
                    "resourceUri": "/subscriptions/ea98974b-5d2a-4d98-a78a-382f3715d07e/"
                                   "resourceGroups/test_emptyrg",
                    "operationName": "Microsoft.Resources/subscriptions/resourceGroups/write",
                    "status": "Succeeded"
                },
                "topic": "/subscriptions/ea98974b-5d2a-4d98-a78a-382f3715d07e"}
