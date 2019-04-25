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

import time

from gcp_common import BaseTest
from googleapiclient.errors import HttpError


class SqlInstanceTest(BaseTest):

    def test_sqlinstance_query(self):
        factory = self.replay_flight_data('sqlinstance-query')
        p = self.load_policy(
            {'name': 'all-sqlinstances',
             'resource': 'gcp.sql-instance'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_sqlinstance_get(self):
        factory = self.replay_flight_data('sqlinstance-get')
        p = self.load_policy(
            {'name': 'one-sqlinstance',
             'resource': 'gcp.sql-instance'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {"project": "cloud-custodian",
             "name": "brenttest-2"})
        self.assertEqual(instance['state'], 'RUNNABLE')

    def test_stop_instance(self):
        project_id = 'cloud-custodian'
        instance_name = 'custodiansqltest'
        factory = self.replay_flight_data('sqlinstance-stop', project_id=project_id)
        p = self.load_policy(
            {'name': 'istop',
             'resource': 'gcp.sql-instance',
             'filters': [{'name': 'custodiansqltest'}],
             'actions': ['stop']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get', {'project': project_id,
                    'instance': instance_name})
        self.assertEqual(result['settings']['activationPolicy'], 'NEVER')

    def test_delete_instance(self):
        project_id = 'cloud-custodian'
        instance_name = 'brenttest-5'
        factory = self.replay_flight_data('sqlinstance-terminate', project_id=project_id)

        p = self.load_policy(
            {'name': 'sqliterm',
             'resource': 'gcp.sql-instance',
             'filters': [{'name': instance_name}],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        try:
            result = client.execute_query(
                'get', {'project': project_id,
                        'instance': instance_name})
            self.fail('found deleted instance: %s' % result)
        except HttpError as e:
            self.assertTrue("does not exist" in str(e))


class SqlDatabaseTest(BaseTest):

    def test_sqldatabase_query(self):
        project_id = 'mitropject'
        session_factory = self.replay_flight_data('sqldatabase-query', project_id=project_id)

        database_name = 'postgres'

        policy = self.load_policy(
            {'name': 'all-sql-databases',
             'resource': 'gcp.sql-database'},
            session_factory=session_factory)

        databases = policy.run()
        self.assertEqual(databases[0]['name'], database_name)

    def test_sqldatabase_get(self):
        project_id = 'mitropject'
        session_factory = self.replay_flight_data('sqldatabase-get', project_id=project_id)

        database_name = 'postgres'
        instance_name = 'testpg'

        policy = self.load_policy(
            {'name': 'one-sql-database',
             'resource': 'gcp.sql-database'},
            session_factory=session_factory)

        resource_manager = policy.resource_manager

        database = resource_manager.get_resource(
            {'project': 'mitropject',
             'name': database_name,
             'instance': instance_name})

        annotation_key = resource_manager.resource_type.get_parent_annotation_key()

        self.assertEqual(database['name'], database_name)
        self.assertEqual(database[annotation_key]['name'], instance_name)
