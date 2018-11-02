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


class InstanceTest(BaseTest):

    def test_instance_query(self):
        factory = self.replay_flight_data('instance-query')
        p = self.load_policy(
            {'name': 'all-instances',
             'resource': 'gcp.instance'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 4)

    def test_instance_get(self):
        factory = self.replay_flight_data('instance-get')
        p = self.load_policy(
            {'name': 'one-instance',
             'resource': 'gcp.instance'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {"instance_id": "2966820606951926687",
             "project_id": "custodian-1291",
             "resourceName": "projects/custodian-1291/zones/us-central1-b/instances/c7n-jenkins",
             "zone": "us-central1-b"})
        self.assertEqual(instance['status'], 'RUNNING')

    def test_stop_instance(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('instance-stop', project_id=project_id)
        p = self.load_policy(
            {'name': 'istop',
             'resource': 'gcp.instance',
             'filters': [{'name': 'instance-1'}, {'status': 'RUNNING'}],
             'actions': ['stop']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = instance-1',
                     'zone': resources[0]['zone'].rsplit('/', 1)[-1]})
        self.assertEqual(result['items'][0]['status'], 'STOPPING')

    def test_delete_instance(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('instance-terminate', project_id=project_id)
        p = self.load_policy(
            {'name': 'iterm',
             'resource': 'gcp.instance',
             'filters': [{'name': 'instance-1'}],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = instance-1',
                     'zone': resources[0]['zone'].rsplit('/', 1)[-1]})
        self.assertEqual(result['items'][0]['status'], 'STOPPING')


class DiskTest(BaseTest):

    def test_disk_query(self):
        factory = self.replay_flight_data('disk-query')
        p = self.load_policy(
            {'name': 'all-disks',
             'resource': 'gcp.disk'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 6)


class SnapshotTest(BaseTest):

    def test_snapshot_query(self):
        factory = self.replay_flight_data(
            'snapshot-query', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'all-disks',
             'resource': 'gcp.snapshot'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_snapshot_delete(self):
        factory = self.replay_flight_data(
            'snapshot-delete', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'all-disks',
             'resource': 'gcp.snapshot',
             'filters': [
                 {'name': 'snapshot-1'}],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
