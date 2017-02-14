# Copyright 2016 Capital One Services, LLC
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

from common import BaseTest


class AlarmTest(BaseTest):

    def test_delete(self):
        alarm = 'c7n-test-alarm-delete'
        factory = self.replay_flight_data('test_alarm_delete')
        client = factory().client('cloudwatch')

        p = self.load_policy(
            {'name': 'delete-alarm',
             'resource': 'alarm',
             'filters': [{
                 'type': 'value',
                 'key': 'AlarmName',
                 'value': alarm + '-*',
                 'op': 'glob'}],
             'actions': ['delete']
             },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 101)
        self.assertEqual(
            client.describe_alarms(
                AlarmNames=[alarm])['MetricAlarms'], [])

    def test_alarm_age(self):
        alarm = 'c7n-test-alarm-age-filter'
        factory = self.replay_flight_data('test_alarm_age_filter')
        client = factory().client('cloudwatch')
        p = self.load_policy({
            'name': 'alarm-age-filter',
            'resource': 'alarm',
            'filters': [{
                'type': 'value',
                'value_type': 'age',
                'key': 'StateUpdatedTimestamp',
                'value': 1,
                'op': 'ge',
            }]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

