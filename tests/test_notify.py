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


class NotifyTest(BaseTest):

    def test_notify(self):
        session_factory = self.replay_flight_data(
            "test_notify_action", zdata=True)
        policy = self.load_policy({
            'name': 'instance-check',
            'resource': 'ec2',
            'filters': [
                {'tag:foi': 'testing'}],
            'actions': [
                {'type': 'notify',
                 'transport' : {
                     'type': 'sqs',
                     'queue': 'https://sqs.us-east-1.amazonaws.com/652117/maid-delivery',
                     }
                 }
                ]
        }, session_factory=session_factory)

        resources = policy.poll()
        self.assertJmes("[].MatchedFilters", resources, [['tag:foi']])
