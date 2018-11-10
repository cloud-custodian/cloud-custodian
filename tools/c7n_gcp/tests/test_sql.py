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

import time
from gcp_common import BaseTest


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
        factory = self.replay_flight_data('sqlinstance-stop', project_id=project_id)
        p = self.load_policy(
            {'name': 'istop',
             'resource': 'gcp.sql-instance',
             'filters': [{'name': 'brenttest-5'}],
             'actions': ['stop']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)

    def test_delete_instance(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('sqlinstance-terminate', project_id=project_id)
        p = self.load_policy(
            {'name': 'iterm',
             'resource': 'gcp.sql-instance',
             'filters': [{'name': 'brenttest-4'}],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id})
        self.assertEqual(len(result['items']), 2)
