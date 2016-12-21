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

from c7n.resources.cfn import Delete

from c7n.executor import MainThreadExecutor


class TestCFN(BaseTest):

    def test_delete(self):
        factory = self.replay_flight_data('test_cfn_delete')
        p = self.load_policy({
            'name': 'cfn-delete',
            'resource': 'cfn',
            'filters': [{'StackStatus': 'ROLLBACK_COMPLETE'}],
            'actions': ['delete']}, session_factory=factory)
        resources = p.run()
        self.maxDiff = None
        self.assertEqual(
            sorted([r['StackName'] for r in resources]),
            ['sphere11-db-1', 'sphere11-db-2', 'sphere11-db-3'])

    def test_query(self):
        factory = self.replay_flight_data('test_cfn_query')
        p = self.load_policy({
            'name': 'cfn-query',
            'resource': 'cfn'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources, [])

    def test_value_filter(self):
        session = self.replay_flight_data('test_cfn_value_filter')
        policy = self.load_policy({
            'name': 'cfn-filter-status',
            'resource': 'cfn',
            'filters': [{
                'StackStatus': 'ROLLBACK_COMPLETE'}]}, session_factory=session)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['StackName'], 'TestStack-2')

    def test_delete_cfn(self):
        self.patch(Delete, 'executor_factory', MainThreadExecutor)
        session = self.replay_flight_data('test_cfn_delete')
        policy = self.load_policy({
            'name': 'cfn-delete-failed',
            'resource': 'cfn',
            'filters': [{
                'StackStatus': 'ROLLBACK_COMPLETE'}]}, session_factory=session)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['StackName'], 'TestStack-2')

        policy = self.load_policy({
            'name': 'cfn-delete-failed',
            'resource': 'cfn',
            'filters': [{
                'StackStatus': 'ROLLBACK_COMPLETE'}],
            'actions': [{
                'type': 'delete'}]}, session_factory=session)
        policy.run()

        policy = self.load_policy({
            'name': 'cfn-delete-failed',
            'resource': 'cfn',
            'filters': [{
                'StackStatus': 'DELETE_IN_PROGRESS'}]}, session_factory=session)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['StackName'], 'TestStack-2')
