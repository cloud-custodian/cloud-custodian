# Copyright 2019 Microsoft Corporation
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


class EventHubTest(BaseTest):

    def test_event_hub_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-event-hub-compliance',
                'resource': 'azure.eventhub'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('eventhub.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-eventhub',
            'resource': 'azure.eventhub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'contains',
                 'value_type': 'normalize',
                 'value': '-cctesteventhubns'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
