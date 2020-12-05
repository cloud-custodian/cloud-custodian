# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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
             "project_id": "cloud-custodian",
             "resourceName": "projects/cloud-custodian/zones/us-central1-b/instances/c7n-jenkins",
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

    def test_label_instance(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('instance-label', project_id=project_id)
        p = self.load_policy(
            {'name': 'ilabel',
             'resource': 'gcp.instance',
             'filters': [{'name': 'test-ingwar'}],
             'actions': [{'type': 'set-labels',
                          'labels': {'test_label': 'test_value'}}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = test-ingwar',
                     'zone': resources[0]['zone'].rsplit('/', 1)[-1]})
        self.assertEqual(result['items'][0]['labels']['test_label'], 'test_value')

    def test_mark_for_op_instance(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('instance-label', project_id=project_id)
        p = self.load_policy(
            {'name': 'ilabel',
             'resource': 'gcp.instance',
             'filters': [{'type': 'marked-for-op',
                          'op': 'stop'}],
             'actions': [{'type': 'mark-for-op',
                          'op': 'start'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = test-ingwar',
                     'zone': resources[0]['zone'].rsplit('/', 1)[-1]})
        self.assertTrue(result['items'][0]['labels']['custodian_status']
                        .startswith("resource_policy-start"))

    def test_detach_disks_from_instance(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('instance-detach-disks', project_id=project_id)
        p = self.load_policy(
            {'name': 'idetach',
             'resource': 'gcp.instance',
             'filters': [{'name': 'test-ingwar'}],
             'actions': [{'type': 'detach-disks'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = test-ingwar',
                     'zone': resources[0]['zone'].rsplit('/', 1)[-1]})
        self.assertIsNone(result['items'][0].get("disks"))

    def test_create_machine_instance_from_instance(self):
        project_id = 'custodian-tests'
        factory = self.replay_flight_data('instance-create-machine-instance', project_id=project_id)
        p = self.load_policy(
            {'name': 'icmachineinstance',
             'resource': 'gcp.instance',
             'filters': [{'name': 'test-ingwar'}],
             'actions': [{'type': 'create-machine-image'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class DiskTest(BaseTest):

    def test_disk_query(self):
        factory = self.replay_flight_data('disk-query', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'all-disks',
             'resource': 'gcp.disk'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 6)

    def test_disk_snapshot(self):
        factory = self.replay_flight_data('disk-snapshot', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'all-images',
             'resource': 'gcp.disk',
             'filters': [
                 {'name': 'c7n-jenkins'}],
             'actions': ['snapshot']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_disk_snapshot_add_date(self):
        factory = self.replay_flight_data('disk-snapshot', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'all-images',
             'resource': 'gcp.disk',
             'filters': [
                 {'name': 'c7n-jenkins'}],
             'actions': [{'type': 'snapshot', 'name_format': "{disk[name]:.50}-{now:%Y-%m-%d}"}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_disk_delete(self):
        project_id = 'cloud-custodian'
        resource_name = 'c7n-jenkins'
        factory = self.replay_flight_data('disk-delete', project_id=project_id)
        policy = self.load_policy(
            {'name': 'all-images',
             'resource': 'gcp.disk',
             'filters': [
                 {'name': resource_name}],
             'actions': ['delete']},
            session_factory=factory)
        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)

        client = policy.resource_manager.get_client()
        zone = resources[0]['zone'].rsplit('/', 1)[-1]
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = instance-1',
                     'zone': zone})

        self.assertEqual(len(result['items']["zones/{}".format(zone)]['disks']), 0)

    def test_label_disk(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('disk-label', project_id=project_id)
        p = self.load_policy(
            {'name': 'disk-label',
             'resource': 'gcp.disk',
             'filters': [{'name': 'test-ingwar'}],
             'actions': [{'type': 'set-labels',
                          'labels': {'test_label': 'test_value'}}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = test-ingwar',
                     'zone': resources[0]['zone'].rsplit('/', 1)[-1]})
        self.assertEqual(result['items'][0]['labels']['test_label'], 'test_value')


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


class AutoscalerTest(BaseTest):

    def test_autoscaler_query(self):
        project_id = 'cloud-custodian'
        resource_name = 'micro-instance-group-1-to-10'
        session_factory = self.replay_flight_data('autoscaler-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-autoscaler-dryrun',
             'resource': 'gcp.autoscaler'},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(resources[0]['name'], resource_name)

    def test_autoscaler_get(self):
        resource_name = 'instance-group-1'
        session_factory = self.replay_flight_data('autoscaler-get')

        policy = self.load_policy(
            {'name': 'gcp-autoscaler-audit',
             'resource': 'gcp.autoscaler',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['v1.compute.autoscalers.insert']
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('autoscaler-insert.json')
        resources = exec_mode.run(event, None)

        self.assertEqual(resources[0]['name'], resource_name)

    def test_autoscaler_set(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('autoscaler-set', project_id=project_id)

        p = self.load_policy(
            {'name': 'gcp-autoscaler-set',
             'resource': 'gcp.autoscaler',
             'filters': [{'name': 'instance-group-2'}],
             'actions': [{'type': 'set',
                          'coolDownPeriodSec': 30,
                          'cpuUtilization': {
                              'utilizationTarget': 0.7
                          },
                          'loadBalancingUtilization': {
                              'utilizationTarget': 0.7
                          },
                          'minNumReplicas': 1,
                          'maxNumReplicas': 4
                          }]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(3)

        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'zone': 'us-central1-a',
                     'filter': 'name = instance-group-2'})

        result_policy = result['items'][0]['autoscalingPolicy']

        self.assertEqual(result_policy['coolDownPeriodSec'], 30)
        self.assertEqual(result_policy['cpuUtilization']['utilizationTarget'], 0.7)
        self.assertEqual(result_policy['loadBalancingUtilization']['utilizationTarget'], 0.7)
        self.assertEqual(result_policy['minNumReplicas'], 1)
        self.assertEqual(result_policy['maxNumReplicas'], 4)
