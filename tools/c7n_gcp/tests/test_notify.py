# Copyright 2015-2019 Capital One Services, LLC
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

from gcp_common import BaseTest


class NotifyTest(BaseTest):

    def test_notify_schema_validate(self):
        factory = self.replay_flight_data('gcpnotifyvalidation')
        p = self.load_policy({
            'name': 'test-notify-for-gcpfunction',
            'resource': 'gcp.function',
            'actions': [
                {'type': 'notify',
                 'template': 'default',
                 'priority_header': '2',
                 'subject': 'testing notify action',
                 'to': ['user@domain.com'],
                 'transport':
                     {'type': 'pubsub',
                      'topic': 'testtopic'}
                 }
            ]}, validate=True, session_factory=factory)
        self.assertTrue(p)

    def test_pubsub_notify(self):
        factory = self.replay_flight_data("notify-action")
        p = self.load_policy({
            'name': 'test-notify',
            'resource': 'gcp.pubsub-topic',
            'filters': [
                {
                    'name': 'projects/cloud-custodian/topics/gcptestnotifytopic'
                }
            ],
            'actions': [
                {'type': 'notify',
                 'template': 'default',
                 'priority_header': '2',
                 'subject': 'testing notify action',
                 'to': ['user@domain.com'],
                 'transport':
                     {'type': 'pubsub',
                      'topic': 'gcptestnotifytopic'}
                 }
            ]}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
