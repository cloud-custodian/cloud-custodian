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

import re
import time

from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError


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

    def test_start_instance(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('instance-start', project_id=project_id)
        p = self.load_policy(
            {'name': 'istart',
             'resource': 'gcp.instance',
             'filters': [{'tag:env': 'dev'}, {'status': 'TERMINATED'}],
             'actions': ['start']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(3)

        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'labels.env=dev',
                     'zone': resources[0]['zone'].rsplit('/', 1)[-1]})
        self.assertEqual(result['items'][0]['status'], 'PROVISIONING')

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


class ImageTest(BaseTest):

    def test_image_query(self):
        factory = self.replay_flight_data(
            'image-query', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'all-images',
             'resource': 'gcp.image'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_image_delete(self):
        factory = self.replay_flight_data(
            'image-delete', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'all-images',
             'resource': 'gcp.image',
             'filters': [
                 {'name': 'image-1'}],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class InstanceTemplateTest(BaseTest):

    def test_instance_template_query(self):
        project_id = 'cloud-custodian'
        resource_name = 'custodian-instance-template'
        session_factory = self.replay_flight_data(
            'instance-template-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-instance-template-dryrun',
             'resource': 'gcp.instance-template'},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(resources[0]['name'], resource_name)

    def test_instance_template_get(self):
        resource_name = 'custodian-instance-template'
        session_factory = self.replay_flight_data(
            'instance-template-get')

        policy = self.load_policy(
            {'name': 'gcp-instance-template-audit',
             'resource': 'gcp.instance-template',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['beta.compute.instanceTemplates.insert']
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('instance-template-create.json')
        resources = exec_mode.run(event, None)
        self.assertEqual(resources[0]['name'], resource_name)

    def test_instance_template_delete(self):
        project_id = 'cloud-custodian'
        resource_name = 'instance-template-to-delete'
        resource_full_name = 'projects/%s/global/instanceTemplates/%s' % (project_id, resource_name)
        session_factory = self.replay_flight_data(
            'instance-template-delete', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-instance-template-delete',
             'resource': 'gcp.instance-template',
             'filters': [{
                 'type': 'value',
                 'key': 'name',
                 'value': resource_name
             }],
             'actions': [{'type': 'delete'}]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)

        if self.recording:
            time.sleep(1)

        client = policy.resource_manager.get_client()
        try:
            result = client.execute_query(
                'get', {'project': project_id,
                        'instanceTemplate': resource_name})
            self.fail('found deleted resource: %s' % result)
        except HttpError as e:
            self.assertTrue(re.match(".*The resource '%s' was not found.*" %
                                     resource_full_name, str(e)))
