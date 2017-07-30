# Copyright 2016-2017 Capital One Services, LLC
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

from .common import BaseTest


class HealthResource(BaseTest):

    def test_health_query(self):
        session_factory = self.replay_flight_data('test_health_query')
        p = self.load_policy({
            'name': 'account-health-query',
            'resource': 'health-event'}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_health_resource_query(self):
        session_factory = self.replay_flight_data('test_health_resource_query')
        p = self.load_policy({
            'name': 'account-health-ec2-query',
            'resource': 'health-event',
            'query': [{'services': 'EC2'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['service'], 'EC2')

    def test_health_augment(self):
        session_factory = self.replay_flight_data('test_health_augment')
        p = self.load_policy({
            'name': 'account-health-augment',
            'resource': 'health-event',
            'query': [{'services': ['BILLING', 'IAM']}]},
                             session_factory=session_factory)
        resources = p.run()
        for r in resources:
            self.assertTrue('Description' in r)
            self.assertTrue(
                (r['eventTypeCategory'] == 'accountNotification'
             ) ^ ('AffectedEntities' in r))
