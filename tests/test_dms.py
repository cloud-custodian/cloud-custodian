# Copyright 2017 Capital One Services, LLC
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

class ReplInstance(BaseTest):

    def test_describe_augment_no_tags(self):
        session_factory = self.replay_flight_data(
            'test_dms_repl_instance_describe_sans_tags')
        p = self.load_policy({
            'name': 'dms-replinstance',
            'resource': 'dms-instance'},
            session_factory=session_factory)        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ReplicationInstanceIdentifier'],
                         'replication-instance-1')

    def test_describe_get_resources(self):
        session_factory = self.replay_flight_data(
            'test_dms_repl_instance_delete')
        p = self.load_policy({
            'name': 'dms-replinstance',
            'resource': 'dms-instance'},
            session_factory=session_factory)        
        resources = p.resource_manager.get_resources(
            ['replication-instance-1'])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ReplicationInstanceIdentifier'],
                         'replication-instance-1')        

    def test_delete(self):
        session_factory = self.replay_flight_data(
            'test_dms_repl_instance_delete')
        client = session_factory().client('dms')
        p = self.load_policy({
            'name': 'dms-replinstance',
            'resource': 'dms-instance',
            'actions': ['delete']},
            session_factory=session_factory)        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ReplicationInstanceIdentifier'],
                         'replication-instance-1')
        instances = client.describe_replication_instances().get(
            'ReplicationInstances')
        self.assertEqual(instances[0]['ReplicationInstanceStatus'], 'deleting')
        
        

