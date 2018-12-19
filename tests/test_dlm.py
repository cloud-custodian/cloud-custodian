# Copyright 2018 Capital One Services, LLC
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

from .common import BaseTest


class DLMPolicyTest(BaseTest):

    def test_dlm_query(self):
        factory = self.replay_flight_data('test_dlm_query')
        p = self.load_policy({
            'name': 'dlm-query', 'resource': 'dlm-policy'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        dlm = resources[0]
        self.maxDiff = None
        self.assertEqual(
            dlm['PolicyDetails'],
            {'ResourceTypes': ['VOLUME'],
             'Schedules': [{
                 'CreateRule': {
                     'Interval': 24,
                     'IntervalUnit': 'HOURS',
                     'Times': ['09:00']},
                 'Name': 'Default Schedule',
                 'RetainRule': {'Count': 5}}],
             'TargetTags': [{'Key': 'App', 'Value': 'Zebra'}]})
