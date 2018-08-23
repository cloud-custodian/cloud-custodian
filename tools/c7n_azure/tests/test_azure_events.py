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


class AzureEventsTest(BaseTest):
    def setUp(self):
        super(AzureEventsTest, self).setUp()

    def test_get_returns_event_dict(self):
        event_dic = AzureEvents.get('VmWrite')
        self.assertEqual(event_dic['event'], 'write')
        self.assertEqual(event_dic['resource_provider'], 'Microsoft.Compute/virtualMachines')

    def test_get_event_operations_one_string(self):
        event_string = 'VmWrite'
        event_operations = AzureEvents.get_event_operations([event_string])
        self.assertEqual(len(event_operations), 1)
        self.assertEqual(event_operations[0], 'Microsoft.Compute/virtualMachines/write')

    def test_get_event_operations_one_event_object(self):
        event_dictionary = {
            'resourceProvider': 'Microsoft.Compute/virtualMachines',
            'event': 'write'
        }
        event_operations = AzureEvents.get_event_operations([event_dictionary])
        self.assertEqual(len(event_operations), 1)
        self.assertEqual(event_operations[0], 'Microsoft.Compute/virtualMachines/write')

    def test_get_event_operations_both_event_types(self):
        event_string = 'AppServicePlanWrite'
        event_dict = {
            'resourceProvider': 'Microsoft.Compute/virtualMachines',
            'event': 'write'
        }
        event_operations = AzureEvents.get_event_operations([event_string, event_dict])
        self.assertEqual(len(event_operations), 2)
        self.assertTrue('Microsoft.Compute/virtualMachines/write' in event_operations)
        self.assertTrue('Microsoft.Web/serverFarms/write' in event_operations)
