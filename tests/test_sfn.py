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


class TestStepFunction(BaseTest):
    def test_sfn_resource(self):
        session_factory = self.replay_flight_data('test_sfn_resource')
        p = self.load_policy(
            {
                'name': 'test-sfn',
                'resource': 'step-machine',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name',
                        'value': 'test'
                    }
                ]
            },
            config={'account_id': '101010101111'},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources), 1)
        self.assertTrue(resources[0]['name'], 'test')
