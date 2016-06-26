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


class DynamodbTest(BaseTest):

    def test_resources(self):
        session_factory = self.replay_flight_data('test_dynamodb_table')
        p = self.load_policy(
            {'name': 'tables',
             'resource': 'dynamodb-table'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['TableName'], 'rolltop')
        self.assertEqual(resources[0]['TableStatus'], 'ACTIVE')

    def test_invoke_action(self):
        session_factory = self.replay_flight_data(
            'test_dynamodb_invoke_action')
        p = self.load_policy(
            {'name': 'tables',
             'resource': 'dynamodb-table',
             'actions': [
                 {'type': 'invoke-lambda',
                  'function': 'process_resources'}
             ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
