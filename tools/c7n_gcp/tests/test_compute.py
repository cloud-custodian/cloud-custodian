# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import re
import time

from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError

from pytest_terraform import terraform


class InstanceTest(BaseTest):

    def test_instance_query(self):
        factory = self.replay_flight_data('instance-query', project_id="cloud-custodian")
        p = self.load_policy(
            {'name': 'all-instances',
             'resource': 'gcp.instance'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 4)
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute:us-east1-b:cloud-custodian:instance/custodian-dev',
                'gcp:compute:us-central1-b:cloud-custodian:instance/c7n-jenkins',
                'gcp:compute:us-central1-b:cloud-custodian:instance/drone',
                'gcp:compute:us-east1-d:cloud-custodian:instance/custodian',
            ],
        )

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

    def test_filter_effective_firewall(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('instance-effective-firewall', project_id=project_id)
        p = self.load_policy(
            {'name': 'test-instance-effective-firewall',
             'resource': 'gcp.instance',
             'filters': [
                 {'type': 'effective-firewall',
                 'key': 'firewalls[*].name',
                 'value': 'default-allow-ssh',
                 'op': 'in',
                 'value_type': 'swap'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_image_filter_iam_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('image-filter-iam', project_id=project_id)
        p = self.load_policy({
            'name': 'image-filter-iam',
            'resource': 'gcp.image',
            'filters': [{
                'type': 'iam-policy',
                'doc': {'key': 'bindings[*].members[]',
                        'op': 'intersect',
                        'value': ['allUsers', 'allAuthenticatedUsers']}
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('image-1', resources[0]['name'])


@terraform('gcp_instance')
def test_instance_pause_resume(test, gcp_instance):
    project_id = 'stacklet-kapilt'
    factory = test.replay_flight_data('instance-pause-resume', project_id=project_id)
    policy = test.load_policy({
        'name': 'gcp-instance',
        'resource': 'gcp.instance',
        'filters': [{'name': gcp_instance['google_compute_instance.default.name']}],
        'actions': ['suspend']
    }, session_factory=factory)

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['status'] == 'RUNNING'

    if test.recording:
        time.sleep(60)

    instance = policy.resource_manager.get_resource({
        "project_id": gcp_instance["google_compute_instance.default.project"],
        "resourceName": gcp_instance["google_compute_instance.default.id"],
        "zone": gcp_instance["google_compute_instance.default.zone"],
    })
    assert instance['status'] == 'SUSPENDED'

    policy = test.load_policy({
        'name': 'gcp-instance',
        'resource': 'gcp.instance',
        'filters': [{'name': gcp_instance['google_compute_instance.default.name']}],
        'actions': ['resume']
    }, session_factory=factory)
    resources = policy.run()
    assert len(resources) == 1

    if test.recording:
        time.sleep(60)

    instance = policy.resource_manager.get_resource({
        "project_id": gcp_instance["google_compute_instance.default.project"],
        "resourceName": gcp_instance["google_compute_instance.default.id"],
        "zone": gcp_instance["google_compute_instance.default.zone"],
    })
    assert instance['status'] == 'RUNNING'


def test_instance_refresh(test):
    factory = test.replay_flight_data('instance-refresh', project_id='cloud-custodian')
    p = test.load_policy(
        {'name': 'all-instances', 'resource': 'gcp.instance'},
        session_factory=factory
    )
    client = p.resource_manager.get_client()
    resource = p.resource_manager.resource_type.refresh(
        client,
        {'selfLink': "https://www.googleapis.com/compute/v1/projects/stacklet-kapilt/zones/us-central1-a/instances/instance-1"}
    )
    assert resource['labels'] == {'env': 'dev'}
    assert resource['labelFingerprint'] == "GHZ1Un204L0="


class DiskTest(BaseTest):

    def test_disk_query(self):
        factory = self.replay_flight_data('disk-query', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'all-disks',
             'resource': 'gcp.disk'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 6)

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute:us-east1-b:cloud-custodian:disk/custodian-dev',
                'gcp:compute:us-east1-c:cloud-custodian:disk/drone-upgrade',
                'gcp:compute:us-east1-d:cloud-custodian:disk/custodian',
                'gcp:compute:us-central1-b:cloud-custodian:disk/c7n-jenkins',
                'gcp:compute:us-central1-b:cloud-custodian:disk/drone',
                'gcp:compute:us-central1-b:cloud-custodian:disk/drone-11-1'
            ],
        )

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

    def test_disk_snapshot_availability(self):
        factory = self.replay_flight_data(
            'disk-snapshot-availability', project_id='cloud-custodian')
        p = self.load_policy(
            {'name': 'test-disk-snapshot-availability',
             'resource': 'gcp.snapshot',
             'filters': [
                 {'type': 'disk-availability'}]},
            session_factory=factory)

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test-snapshot')

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

    def test_recommend_disk(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('disk-recommend', project_id=project_id)
        p = self.load_policy({
            'name': 'disk-label',
            'resource': 'gcp.disk',
            'filters': [{'type': 'recommend',
                         'id': 'google.compute.disk.IdleResourceRecommender'}]},
            session_factory=factory)
        assert p.get_permissions() == {
            'compute.disks.list',
            'recommender.computeDiskIdleResourceRecommendations.get',
            'recommender.computeDiskIdleResourceRecommendations.list'
        }
        resources = p.run()
        assert len(resources) == 2
        assert resources[0]['c7n:recommend'][0]['recommenderSubtype'] == 'SNAPSHOT_AND_DELETE_DISK'


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

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:snapshot/snapshot-1'
            ],
        )

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
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:snapshot/snapshot-1'
            ],
        )


def test_image_refresh(test):
    factory = test.replay_flight_data('image-refresh', project_id='cloud-custodian')
    p = test.load_policy(
        {'name': 'all-images', 'resource': 'gcp.image'},
        session_factory=factory
    )
    client = p.resource_manager.get_client()
    resource = p.resource_manager.resource_type.refresh(
        client,
        {'selfLink': 'https://www.googleapis.com/compute/v1/projects/stacklet-kapilt/global/images/image-1-dev'}
    )
    assert resource['labels'] == {'env': 'dev'}
    assert resource['labelFingerprint'] == "GHZ1Un204L0="


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

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:image/image-1'
            ],
        )

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

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:image/image-1'
            ],
        )

    def test_label_image(self):
        project_id = 'cloud-custodian'
        image_name = 'image-1'
        factory = self.replay_flight_data(
            'image-set-label', project_id)
        p = self.load_policy(
            {'name': 'label-image',
            'resource': 'gcp.image',
            'filters': [
                {'name': image_name}],
            'actions': [{'type': 'set-labels',
                        'labels': {'test_label': 'test_value'}}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = image-1'})
        self.assertEqual(result['items'][0]['labels']['test_label'], 'test_value')

    def test_unlabel_image(self):
        project_id = 'cloud-custodian'
        image_name = 'image-1'
        factory = self.replay_flight_data(
            'image-remove-label', project_id)
        p = self.load_policy(
            {'name': 'label-image',
            'resource': 'gcp.image',
            'filters': [
                {'name': image_name}],
            'actions': [{'type': 'set-labels',
                        'remove': ['test_label']}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'project': project_id,
                     'filter': 'name = image-1'})
        self.assertEqual(result['items'][0]['labels'].get('test_label'), None)


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
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:instance-template/custodian-instance-template'
            ],
        )

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
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                'gcp:compute::cloud-custodian:instance-template/custodian-instance-template'
            ],
        )

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
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                # NOTE: zonal resource
                'gcp:compute:us-central1-a:cloud-custodian:autoscaler/micro-instance-group-1-to-10'
            ],
        )

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
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                # NOTE: zonal resource
                'gcp:compute:us-central1-a:cloud-custodian:autoscaler/instance-group-1'
            ],
        )

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


class ProjectTest(BaseTest):

    def test_projects(self):
        project_id = 'gcp-lab-custodian'
        session_factory = self.replay_flight_data('project-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-projects',
             'resource': 'gcp.compute-project'},
            session_factory=session_factory)
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'gcp-lab-custodian')


class TestInstanceGroupManager(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            'test_instance_group_manager_query', project_id=project_id)
        p = self.load_policy(
            {'name': 'gcp-instance-group-manager',
             'resource': 'gcp.instance-group-manager'},
            session_factory=factory)

        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('instance-group-2', resources[0]['name'])
