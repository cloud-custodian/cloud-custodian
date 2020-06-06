# Copyright 2020 Kapil Thangavelu
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


class SARTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('test_sar_query_app')
        p = self.load_policy({
            'name': 'test-sar',
            'resource': 'aws.serverless-app'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'GitterArchive')

    def test_cross_account(self):
        factory = self.replay_flight_data('test_sar_cross_account')
        p = self.load_policy({
            'name': 'test-sar',
            'resource': 'aws.serverless-app',
            'filters': [{
                'type': 'cross-account',
                'whitelist_orgids': ['o-4adkskbcff']
            }]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.maxDiff = None
        self.assertEqual(
            resources[0]['CrossAccountViolations'], [
                {'Actions': ['serverlessrepo:Deploy'],
                 'Effect': 'Allow',
                 'Principal': {'AWS': ['112233445566']},
                 'StatementId': 'b364d84f-62d2-411c-9787-3636b2b1975c'}
            ])
