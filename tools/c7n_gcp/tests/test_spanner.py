# Copyright 2019 Capital One Services, LLC
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

from gcp_common import BaseTest, event_data
import time

class SpannerInstanceTest(BaseTest):
    def test_spanner_instance_query(self):
        project_id = 'atomic-shine-231410'
        session_factory = self.replay_flight_data('spanner-instance-query', project_id=project_id)

        policy = {
            'name': 'all-spanner-instances',
            'resource': 'gcp.spanner-instance'
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['displayName'], 'test-instance')

    def test_spanner_instance_get(self):
        session_factory = self.replay_flight_data('spanner-instance-get')
        policy = self.load_policy(
            {'name': 'one-spanner-instance',
             'resource': 'gcp.spanner-instance',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('spanner-instance-get.json')
        instances = exec_mode.run(event, None)

        self.assertEqual(instances[0]['state'], 'READY')
        self.assertEqual(instances[0]['config'],
                         'projects/custodian-test-project-0/instanceConfigs/regional-asia-east1')
        self.assertEqual(instances[0]['name'],
                         'projects/custodian-test-project-0/instances/custodian-spanner-1')

    def test_spanner_instance_delete(self):
        project_id = 'custodian-test-project-0'
        deleting_instance_name = 'spanner-instance-0'
        non_deleting_instance_name = 'spanner-instance-1'
        session_factory = self.replay_flight_data('spanner-instance-delete',
                                                  project_id=project_id)
        policy = self.load_policy(
            {'name': 'spanner-instance-delete',
             'resource': 'gcp.spanner-instance',
             'filters': [{'displayName': deleting_instance_name}],
             'actions': ['delete']},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['displayName'], deleting_instance_name)

        session_factory = self.replay_flight_data('spanner-instance-after-delete',
                                                  project_id=project_id)
        policy = self.load_policy(
            {'name': 'spanner-instance-after-delete',
             'resource': 'gcp.spanner-instance'},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['displayName'], non_deleting_instance_name)

    def test_spanner_instance_patch(self):
        project_id = 'custodian-test-project-0'
        patching_instance_name = 'spanner-instance-0'
        non_patching_instance_name = 'spanner-instance-1'
        session_factory = self.replay_flight_data('spanner-instance-patch',
                                                  project_id=project_id)
        policy = self.load_policy(
            {'name': 'spanner-instance-patch',
             'resource': 'gcp.spanner-instance',
             'filters': [{
                 'type': 'value',
                 'key': 'nodeCount',
                 'value': 1,
                 'op': 'greater-than'}],
             'actions': [{
                 'type': 'patch',
                 'nodeCount': 1
             }]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['displayName'], patching_instance_name)

        session_factory = self.replay_flight_data('spanner-instance-after-patch',
                                                  project_id=project_id)
        policy = self.load_policy(
            {'name': 'spanner-instances-after-patch',
             'resource': 'gcp.spanner-instance'},
            session_factory=session_factory)
        time.sleep(1)
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['displayName'], patching_instance_name)
        self.assertEqual(resources[1]['displayName'], non_patching_instance_name)
        self.assertEqual(resources[0]['nodeCount'], 1)
        self.assertEqual(resources[1]['nodeCount'], 1)

class SpannerDatabaseInstanceTest(BaseTest):

    def test_spanner_database_instance_query(self):
        project_id = 'custodiantestproject'
        session_factory = self.replay_flight_data('spanner-database-instance-query',
                                                  project_id=project_id)

        policy = self.load_policy(
            {'name': 'all-spanner-database-instances',
             'resource': 'gcp.spanner-database-instance'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['c7n:spanner-instance']['displayName'], 'custodian-spanner')
        self.assertEqual(resources[0]['c7n:spanner-instance']['state'], 'READY')
        self.assertEqual(resources[0]['c7n:spanner-instance']['nodeCount'], 1)

    def test_spanner_database_instance_get(self):
        session_factory = self.replay_flight_data('spanner-database-instance-get')
        policy = self.load_policy(
            {'name': 'one-spanner-database-instance',
             'resource': 'gcp.spanner-database-instance',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('spanner-database-instance-get.json')

        instances = exec_mode.run(event, None)

        self.assertEqual(instances[0]['state'], 'READY')
        self.assertEqual(instances[0]['c7n:spanner-instance']['displayName'], 'custodian-spanner-1')
        self.assertEqual(instances[0]['c7n:spanner-instance']['name'],
                         'projects/custodian-test-project-0/instances/custodian-spanner-1')
