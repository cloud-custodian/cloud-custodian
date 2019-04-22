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

from gcp_common import BaseTest


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
        project_id = 'custodiantestproject'
        session_factory = self.replay_flight_data('spanner-instance-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'one-spanner-instance',
             'resource': 'gcp.spanner-instance'},
            session_factory=session_factory)

        instance = policy.resource_manager.get_resource(
            {'resourceName': 'projects/custodiantestproject/instances/custodian-spanner'})

        self.assertEqual(instance['state'], 'READY')


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
        project_id = 'custodiantestproject'
        session_factory = self.replay_flight_data('spanner-database-instance-get',
                                                  project_id=project_id)

        resource_name = 'projects/custodiantestproject/instances/spanner-instance' \
                        '/databases/custodian-database'

        policy = self.load_policy(
            {'name': 'one-spanner-database-instance',
             'resource': 'gcp.spanner-database-instance'},
            session_factory=session_factory)

        instance = policy.resource_manager.get_resource({'resourceName': resource_name})

        self.assertEqual(instance['state'], 'READY')
        self.assertEqual(instance['c7n:spanner-instance']['displayName'], 'spanner-instance')
        self.assertEqual(instance['c7n:spanner-instance']['name'],
                         'projects/custodiantestproject/instances/spanner-instance')
        self.assertEqual(instance['name'], resource_name)
