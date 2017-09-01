# Copyright 2016-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest, functional

import uuid
import time

class ElasticFileSystem(BaseTest):

    @functional
    def test_resource_manager(self):
        factory = self.replay_flight_data('test_efs_query')
        client = factory().client('efs')
        token = str(uuid.uuid4())
        fs_id = client.create_file_system(
            CreationToken=token).get('FileSystemId')
        tags = [{'Key': 'Name', 'Value': 'Somewhere'}]
        client.create_tags(FileSystemId=fs_id, Tags=tags)
        if self.recording:
            time.sleep(5)
            self.addCleanup(client.delete_file_system, FileSystemId=fs_id)

        p = self.load_policy({
            'name': 'efs-query',
            'resource': 'efs',
            'filters': [{'tag:Name': 'Somewhere'}],
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Tags'], tags)

    def test_mount_target_loading(self):
        factory = self.replay_flight_data('test_efs_subresource')
        p = self.load_policy({
            'name': 'test-mount-targets',
            'resource': 'efs-mount-target',
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_delete(self):
        factory = self.replay_flight_data('test_efs_delete')
        p = self.load_policy({
            'name': 'efs-query',
            'resource': 'efs',
            'filters': [{'Name': 'MyDocs'}],
            'actions': ['delete']
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'MyDocs')
        client = factory().client('efs')
        state = client.describe_file_systems().get('FileSystems', [])
        self.assertEqual(state, [])

