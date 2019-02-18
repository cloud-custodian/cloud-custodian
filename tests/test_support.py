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


class TestSupportCase(BaseTest):
    def test_support_resource(self):
        session_factory = self.replay_flight_data('test_support_resource')
        p = self.load_policy(
            {
                'name': 'test-support',
                'resource': 'support-case',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'caseId',
                        'value': 'case-101010101111-muen-2019-eadc0ea0c6ea6705'
                    }
                ]
            },
            config={'account_id': '101010101111'},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['caseId'], 'case-101010101111-muen-2019-eadc0ea0c6ea6705')
        self.assertEqual(
            p.resource_manager.get_arns(resources),
            ['arn:::case-101010101111-muen-2019-eadc0ea0c6ea6705'])
