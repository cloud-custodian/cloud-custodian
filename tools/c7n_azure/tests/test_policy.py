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

import json

from azure_common import BaseTest
from c7n_azure.policy import AzureEventMode
from c7n_azure.azure_events import AzureEvents
from c7n_azure.constants import CONST_AZURE_EVENT_TRIGGER_MODE


class FunctionPackageTest(BaseTest):
    def setUp(self):
        super(FunctionPackageTest, self).setUp()

    def test_event_mode_is_subscribed_to_event_true(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
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

        event_mode = AzureEventMode(p)
        self.assertTrue(event_mode.is_subscribed_to_event(event, subscribed_events))

    def test_event_mode_is_subscribed_to_event_false(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
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
        event_mode = AzureEventMode(p)
        self.assertFalse(event_mode.is_subscribed_to_event(event, subscribed_events))

