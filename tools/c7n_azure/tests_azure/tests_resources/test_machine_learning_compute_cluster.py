# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import time
from unittest.mock import ANY, call, Mock, patch

import requests

from azure.core.exceptions import HttpResponseError
from azure.mgmt.machinelearningservices.models import (
    AmlCompute,
    AmlComputeProperties,
    ComputeInstance,
    ComputeInstanceProperties,
    ComputeResource,
    NodeStateCounts,
    ScaleSettings,
)

from c7n.exceptions import PolicyValidationError
from c7n.utils import local_session
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser

from ..azure_common import (
    BaseTest,
    arm_template,
    cassette_name,
)


class MachineLearningComputeClusterTest(BaseTest):

    recording_resource_group = 'test_machine-learning-compute-cluster'
    parent_id = (
        '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/'
        'resourceGroups/test-rg/providers/Microsoft.MachineLearningServices/'
        'workspaces/test-workspace'
    )

    def _load_inactive_filter(self, since='1d'):
        policy = self.load_policy({
            'name': 'inactive-machine-learning-compute-clusters',
            'resource': 'azure.machine-learning-compute-cluster',
            'filters': [{
                'type': 'inactive',
                'since': since,
            }],
        })
        return policy.resource_manager.filters[0]

    def _load_set_min_nodes_action(self):
        policy = self.load_policy({
            'name': 'set-machine-learning-compute-cluster-minimum-nodes',
            'resource': 'azure.machine-learning-compute-cluster',
            'actions': [{
                'type': 'set-min-nodes',
                'value': 0,
            }],
        })
        return policy.resource_manager.actions[0]

    def _scale_cluster(self):
        return {
            'id': f'{self.parent_id}/computes/test-cluster',
            'name': 'test-cluster',
            'c7n:parent-id': self.parent_id,
            'properties': {
                'properties': {
                    'scaleSettings': {
                        'minNodeCount': 1,
                        'maxNodeCount': 4,
                        'nodeIdleTimeBeforeScaleDown': 'PT5M',
                    },
                },
            },
        }

    def _cluster(
        self,
        name,
        running_node_count=0,
        parent_id=None,
        discovery_url='https://westus.api.azureml.ms/discovery',
    ):
        return {
            'name': name,
            'c7n:parent-id': parent_id or self.parent_id,
            'c7n:WorkspaceDiscoveryUrl': discovery_url,
            'properties': {
                'properties': {
                    'nodeStateCounts': {
                        'runningNodeCount': running_node_count,
                    },
                },
            },
        }

    def test_machine_learning_compute_cluster_schema_validate(self):
        p = self.load_policy({
            'name': 'machine-learning-compute-clusters',
            'resource': 'azure.machine-learning-compute-cluster',
        }, validate=True)
        self.assertTrue(p)

    @arm_template('machine-learning-compute-cluster.json')
    @cassette_name('machine-learning-compute-cluster-query')
    def test_machine_learning_compute_cluster_policy_query(self):
        policy = self.load_policy({
            'name': 'find-machine-learning-compute-cluster',
            'resource': 'azure.machine-learning-compute-cluster',
            'filters': [
                {
                    'type': 'value',
                    'key': 'resourceGroup',
                    'value': 'test_machine-learning-compute-cluster',
                },
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctest-ml-cluster',
                },
                {
                    'type': 'value',
                    'key': 'properties.computeType',
                    'value': 'AmlCompute',
                },
            ],
        })

        resources = policy.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('cctest-ml-cluster', resources[0]['name'])
        self.assertEqual(
            'test_machine-learning-compute-cluster',
            resources[0]['resourceGroup'],
        )

    def test_machine_learning_compute_cluster_child_query(self):
        parent_id = (
            '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/'
            'resourceGroups/test-rg/providers/Microsoft.MachineLearningServices/'
            'workspaces/test-workspace'
        )
        cluster_properties = AmlComputeProperties(
            vm_size='Standard_DS2_v2',
            scale_settings=ScaleSettings(
                max_node_count=4,
                min_node_count=1,
                node_idle_time_before_scale_down=datetime.timedelta(minutes=5),
            ),
        )
        cluster_properties.current_node_count = 2
        cluster_properties.node_state_counts = NodeStateCounts()
        cluster_properties.node_state_counts.running_node_count = 1
        cluster = ComputeResource(
            properties=AmlCompute(properties=cluster_properties),
            location='westus',
        )
        cluster.id = f'{parent_id}/computes/test-cluster'
        cluster.name = 'test-cluster'
        cluster.type = 'Microsoft.MachineLearningServices/workspaces/computes'

        instance = ComputeResource(
            properties=ComputeInstance(
                properties=ComputeInstanceProperties(vm_size='Standard_DS2_v2'),
            ),
            location='westus',
        )
        instance.id = f'{parent_id}/computes/test-instance'
        instance.name = 'test-instance'
        instance.type = 'Microsoft.MachineLearningServices/workspaces/computes'

        parent_manager = Mock()
        parent_manager.resource_type.id = 'id'
        parent_manager.resources.return_value = [{
            'id': parent_id,
            'name': 'test-workspace',
            'resourceGroup': 'test-rg',
            'properties': {
                'discoveryUrl': 'https://westus.api.azureml.ms/discovery',
            },
        }]

        client = Mock()
        client.compute.list.return_value = [cluster, instance]

        p = self.load_policy({
            'name': 'machine-learning-compute-clusters',
            'resource': 'azure.machine-learning-compute-cluster',
        })
        manager = p.resource_manager
        manager.get_parent_manager = Mock(return_value=parent_manager)
        manager.get_client = Mock(return_value=client)

        resources = manager.resources()

        client.compute.list.assert_called_once_with(
            resource_group_name='test-rg',
            workspace_name='test-workspace',
        )
        self.assertEqual(['test-cluster'], [r['name'] for r in resources])
        self.assertEqual(parent_id, resources[0]['c7n:parent-id'])
        self.assertEqual(
            'https://westus.api.azureml.ms/discovery',
            resources[0]['c7n:WorkspaceDiscoveryUrl'],
        )
        properties = resources[0]['properties']['properties']
        self.assertEqual(2, properties['currentNodeCount'])
        self.assertEqual(1, properties['nodeStateCounts']['runningNodeCount'])
        self.assertEqual(1, properties['scaleSettings']['minNodeCount'])
        self.assertEqual(4, properties['scaleSettings']['maxNodeCount'])

    def test_child_query_defaults_missing_discovery_url(self):
        policy = self.load_policy({
            'name': 'machine-learning-compute-clusters',
            'resource': 'azure.machine-learning-compute-cluster',
        })
        cluster = {
            'name': 'test-cluster',
            'properties': {'computeType': 'AmlCompute'},
        }
        parent = {
            'name': 'test-workspace',
            'resourceGroup': 'test-rg',
            'properties': {},
        }

        with patch(
            'c7n_azure.resources.arm.ChildArmResourceManager.'
            'enumerate_resources',
            return_value=[cluster],
        ):
            resources = policy.resource_manager.enumerate_resources(
                parent,
                policy.resource_manager.resource_type,
            )

        self.assertIsNone(resources[0]['c7n:WorkspaceDiscoveryUrl'])

    def _run_inactive_policy(self, since):
        policy = self.load_policy({
            'name': 'find-inactive-machine-learning-compute-cluster',
            'resource': 'azure.machine-learning-compute-cluster',
            'filters': [
                {
                    'type': 'value',
                    'key': 'resourceGroup',
                    'value': 'test_machine-learning-compute-cluster',
                },
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctest-ml-cluster',
                },
                {
                    'type': 'inactive',
                    'since': since,
                },
            ],
        })
        return policy.run()

    @arm_template('machine-learning-compute-cluster.json')
    @cassette_name('machine-learning-compute-cluster-inactive-current')
    def test_machine_learning_compute_cluster_inactive_current_policy(self):
        resources = self._run_inactive_policy('1m')

        self.assertEqual([], resources)

    @arm_template('machine-learning-compute-cluster.json')
    @cassette_name('machine-learning-compute-cluster-inactive-recent')
    def test_machine_learning_compute_cluster_inactive_recent_policy(self):
        resources = self._run_inactive_policy('1d')

        self.assertEqual([], resources)

    def test_set_min_nodes_schema_validate(self):
        policy = self.load_policy({
            'name': 'set-machine-learning-compute-cluster-minimum-nodes',
            'resource': 'azure.machine-learning-compute-cluster',
            'actions': [{
                'type': 'set-min-nodes',
                'value': 0,
            }],
        }, validate=True)

        self.assertTrue(policy)

    def test_set_min_nodes_schema_rejects_invalid_values(self):
        for action in (
            {'type': 'set-min-nodes'},
            {'type': 'set-min-nodes', 'value': -1},
            {'type': 'set-min-nodes', 'value': 1.5},
            {'type': 'set-min-nodes', 'value': 0, 'state': 'idle'},
        ):
            with self.subTest(action=action):
                with self.assertRaises(PolicyValidationError):
                    self.load_policy({
                        'name': 'set-machine-learning-compute-cluster-minimum-nodes',
                        'resource': 'azure.machine-learning-compute-cluster',
                        'actions': [action],
                    }, validate=True)

    @arm_template('machine-learning-compute-cluster.json')
    @cassette_name('machine-learning-compute-cluster-set-min-nodes')
    def test_set_min_nodes_policy(self):
        resource_group = 'test_machine-learning-compute-cluster'
        cluster_name = 'cctest-ml-cluster'
        query_policy = self.load_policy({
            'name': 'get-machine-learning-compute-cluster-for-update',
            'resource': 'azure.machine-learning-compute-cluster',
            'filters': [
                {
                    'type': 'value',
                    'key': 'resourceGroup',
                    'value': resource_group,
                },
                {
                    'type': 'value',
                    'key': 'name',
                    'value': cluster_name,
                },
            ],
        })
        clusters = query_policy.run()
        self.assertEqual(1, len(clusters))
        workspace_name = ResourceIdParser.get_resource_name(
            clusters[0]['c7n:parent-id']
        )
        client = local_session(Session).client(
            'azure.mgmt.machinelearningservices.'
            'MachineLearningServicesMgmtClient'
        )
        setup_policy = self.load_policy({
            'name': 'prepare-machine-learning-compute-cluster-minimum-nodes',
            'resource': 'azure.machine-learning-compute-cluster',
            'filters': [
                {
                    'type': 'value',
                    'key': 'resourceGroup',
                    'value': resource_group,
                },
                {
                    'type': 'value',
                    'key': 'name',
                    'value': cluster_name,
                },
            ],
            'actions': [{
                'type': 'set-min-nodes',
                'value': 1,
            }],
        })
        self.assertEqual(1, len(setup_policy.run()))
        for _ in range(60):
            cluster = client.compute.get(
                resource_group,
                workspace_name,
                cluster_name,
            )
            scale_settings = cluster.properties.properties.scale_settings
            if (
                cluster.properties.provisioning_state == 'Succeeded'
                and scale_settings.min_node_count == 1
            ):
                break
            if not self.is_playback():
                time.sleep(5)
        else:
            self.fail('compute cluster did not reach minimum one')

        action_policy = self.load_policy({
            'name': 'set-machine-learning-compute-cluster-minimum-nodes',
            'resource': 'azure.machine-learning-compute-cluster',
            'filters': [
                {
                    'type': 'value',
                    'key': 'resourceGroup',
                    'value': resource_group,
                },
                {
                    'type': 'value',
                    'key': 'name',
                    'value': cluster_name,
                },
                {
                    'type': 'value',
                    'key': 'properties.properties.scaleSettings.minNodeCount',
                    'value': 1,
                },
            ],
            'actions': [{
                'type': 'set-min-nodes',
                'value': 0,
            }],
        })
        resources = action_policy.run()
        self.assertEqual(1, len(resources))

        cluster = client.compute.get(
            resource_group,
            workspace_name,
            cluster_name,
        )
        scale_settings = cluster.properties.properties.scale_settings
        self.assertEqual(0, scale_settings.min_node_count)
        self.assertEqual(1, scale_settings.max_node_count)
        self.assertEqual(
            datetime.timedelta(minutes=2),
            scale_settings.node_idle_time_before_scale_down,
        )

    def test_set_min_nodes_accepts_accepted_response(self):
        action = self._load_set_min_nodes_action()
        client = Mock()
        client.compute.begin_update.side_effect = HttpResponseError(
            response=Mock(status_code=202, reason='Accepted'),
        )
        action.manager.get_client = Mock(return_value=client)

        action._prepare_processing()
        action._process_resource(self._scale_cluster())

        client.compute.begin_update.assert_called_once()

    def test_set_min_nodes_reraises_non_accepted_response(self):
        action = self._load_set_min_nodes_action()
        error = HttpResponseError(
            response=Mock(status_code=409, reason='Conflict'),
        )
        client = Mock()
        client.compute.begin_update.side_effect = error
        action.manager.get_client = Mock(return_value=client)

        action._prepare_processing()
        with self.assertRaises(HttpResponseError) as caught:
            action._process_resource(self._scale_cluster())

        self.assertIs(error, caught.exception)

    def test_set_min_nodes_exact_update_request(self):
        action = self._load_set_min_nodes_action()
        client = Mock()
        action.manager.get_client = Mock(return_value=client)

        action._prepare_processing()
        action._process_resource(self._scale_cluster())

        self.assertEqual(1, client.compute.begin_update.call_count)
        kwargs = client.compute.begin_update.call_args.kwargs
        self.assertEqual('test-rg', kwargs['resource_group_name'])
        self.assertEqual('test-workspace', kwargs['workspace_name'])
        self.assertEqual('test-cluster', kwargs['compute_name'])
        scale = kwargs['parameters'].properties.scale_settings
        self.assertEqual(0, scale.min_node_count)
        self.assertEqual(4, scale.max_node_count)
        self.assertEqual(
            datetime.timedelta(minutes=5),
            scale.node_idle_time_before_scale_down,
        )
        self.assertEqual(
            {
                'properties': {
                    'properties': {
                        'scaleSettings': {
                            'minNodeCount': 0,
                            'maxNodeCount': 4,
                            'nodeIdleTimeBeforeScaleDown': 'PT5M',
                        },
                    },
                },
            },
            kwargs['parameters'].serialize(),
        )

    def test_set_min_nodes_keeps_unset_idle_time_unset(self):
        action = self._load_set_min_nodes_action()
        client = Mock()
        action.manager.get_client = Mock(return_value=client)
        resource = self._scale_cluster()
        del resource['properties']['properties']['scaleSettings'][
            'nodeIdleTimeBeforeScaleDown'
        ]

        action._prepare_processing()
        action._process_resource(resource)

        kwargs = client.compute.begin_update.call_args.kwargs
        self.assertEqual(
            {
                'properties': {
                    'properties': {
                        'scaleSettings': {
                            'minNodeCount': 0,
                            'maxNodeCount': 4,
                        },
                    },
                },
            },
            kwargs['parameters'].serialize(),
        )

    def test_inactive_schema_validate(self):
        policy = self.load_policy({
            'name': 'inactive-machine-learning-compute-clusters',
            'resource': 'azure.machine-learning-compute-cluster',
            'filters': [{
                'type': 'inactive',
                'since': '1d',
            }],
        }, validate=True)

        self.assertTrue(policy)

    def test_inactive_schema_rejects_invalid_values(self):
        for inactive_filter in (
            {'type': 'inactive'},
            {'type': 'inactive', 'since': '0d'},
            {'type': 'inactive', 'since': '-1d'},
            {'type': 'inactive', 'since': '1y'},
            {'type': 'inactive', 'since': '1d', 'state': 'idle'},
        ):
            with self.subTest(inactive_filter=inactive_filter):
                with self.assertRaises(PolicyValidationError):
                    self.load_policy({
                        'name': 'inactive-machine-learning-compute-clusters',
                        'resource': 'azure.machine-learning-compute-cluster',
                        'filters': [inactive_filter],
                    }, validate=True)

    def test_inactive_short_circuit_running_clusters(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._get_active_targets = Mock(return_value=set())
        clusters = [
            self._cluster('running-cluster', running_node_count=1),
            self._cluster('idle-cluster'),
        ]

        resources = inactive_filter.process(clusters)

        self.assertEqual(['idle-cluster'], [r['name'] for r in resources])
        inactive_filter._get_active_targets.assert_called_once()

    def test_inactive_short_circuit_skips_history_for_running_clusters(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._get_active_targets = Mock(return_value=set())

        resources = inactive_filter.process([
            self._cluster('running-cluster', running_node_count=1),
        ])

        self.assertEqual([], resources)
        inactive_filter._get_active_targets.assert_not_called()

    def test_inactive_cluster_without_node_state_counts(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._get_active_targets = Mock(return_value=set())
        cluster = self._cluster('provisioning-cluster')
        cluster['properties'] = {}

        resources = inactive_filter.process([cluster])

        self.assertEqual(['provisioning-cluster'], [r['name'] for r in resources])

    @patch(
        'c7n_azure.resources.machine_learning_compute_cluster.utils.requests_session',
    )
    def test_inactive_history_pagination(self, requests_session):
        inactive_filter = self._load_inactive_filter()
        azure_session = Mock()
        azure_session.cloud_endpoints.name = 'AzureCloud'
        inactive_filter.manager.get_session = Mock(return_value=azure_session)
        first_response = Mock()
        first_response.json.return_value = {
            'value': [{'experimentId': 'first'}],
            'continuationToken': 'next-page',
        }
        second_response = Mock()
        second_response.json.return_value = {
            'value': [{'experimentId': 'second'}],
            'continuationToken': None,
        }
        http = requests_session.return_value
        http.post.side_effect = [first_response, second_response]
        url = 'https://westus.api.azureml.ms/history/v1.0/experiments:query'

        values = inactive_filter._query_history(
            url,
            {'viewType': 'ActiveOnly'},
        )

        self.assertEqual(
            [{'experimentId': 'first'}, {'experimentId': 'second'}],
            values,
        )
        requests_session.assert_called_once_with(
            azure_session,
            token_scope='https://ml.azure.com/.default',
            max_retries=3,
            allowed_methods=('POST',),
        )
        self.assertEqual(2, http.post.call_count)
        self.assertEqual(
            {'api-version': '2023-10-01'},
            http.post.call_args_list[0].kwargs['params'],
        )
        self.assertEqual(
            {'viewType': 'ActiveOnly'},
            http.post.call_args_list[0].kwargs['json'],
        )
        self.assertEqual(
            {
                'viewType': 'ActiveOnly',
                'continuationToken': 'next-page',
            },
            http.post.call_args_list[1].kwargs['json'],
        )
        for post_call in http.post.call_args_list:
            self.assertEqual(30, post_call.kwargs['timeout'])
            self.assertEqual(
                {'Content-Type': 'application/json'},
                post_call.kwargs['headers'],
            )
        first_response.raise_for_status.assert_called_once_with()
        second_response.raise_for_status.assert_called_once_with()

    @patch(
        'c7n_azure.resources.machine_learning_compute_cluster.utils.requests_session',
    )
    def test_inactive_history_pagination_rejects_missing_value(
        self,
        requests_session,
    ):
        inactive_filter = self._load_inactive_filter()
        azure_session = Mock()
        azure_session.cloud_endpoints.name = 'AzureCloud'
        inactive_filter.manager.get_session = Mock(return_value=azure_session)
        response = Mock()
        response.json.return_value = {}
        requests_session.return_value.post.return_value = response

        with self.assertRaises(TypeError):
            inactive_filter._query_history(
                'https://westus.api.azureml.ms/history/v1.0/experiments:query',
                {'viewType': 'ActiveOnly'},
            )

        response.raise_for_status.assert_called_once_with()

    @patch(
        'c7n_azure.resources.machine_learning_compute_cluster.utils.requests_session',
    )
    def test_inactive_history_audience_follows_cloud(self, requests_session):
        inactive_filter = self._load_inactive_filter()
        azure_session = Mock()
        inactive_filter.manager.get_session = Mock(return_value=azure_session)
        requests_session.return_value.post.return_value.json.return_value = {
            'value': [],
        }

        for cloud, audience in (
            ('AzureCloud', 'https://ml.azure.com/.default'),
            ('AzureChinaCloud', 'https://ml.azure.cn/.default'),
            ('AzureUSGovernment', 'https://ml.azure.us/.default'),
        ):
            with self.subTest(cloud=cloud):
                azure_session.cloud_endpoints.name = cloud
                requests_session.reset_mock()

                inactive_filter._query_history(
                    'https://westus.api.azureml.ms/history/v1.0/runs:query',
                    {},
                )

                requests_session.assert_called_once_with(
                    azure_session,
                    token_scope=audience,
                    max_retries=3,
                    allowed_methods=('POST',),
                )

    def test_inactive_experiments_include_archived(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._query_history = Mock(return_value=[
            {'experimentId': 'active'},
            {'experimentId': 'archived'},
            {'experimentId': 'archived'},
            {'experimentId': ''},
        ])

        experiments = inactive_filter._get_experiments(self._cluster('cluster'))

        self.assertEqual(['active', 'archived'], experiments)
        url = (
            f'https://westus.api.azureml.ms/history/v1.0{self.parent_id}/'
            'experiments:query'
        )
        self.assertEqual(
            [call(url, {'viewType': 'All'})],
            inactive_filter._query_history.call_args_list,
        )

    def test_inactive_active_targets_include_standalone_and_pipeline_runs(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._get_experiments = Mock(
            return_value=['experiment-one', 'experiment-two'],
        )
        inactive_filter._query_history = Mock(side_effect=[
            [
                {'runId': 'standalone', 'target': 'Cluster-One'},
                {'runId': 'pipeline-parent', 'target': None},
            ],
            [{'runId': 'pipeline-child', 'target': 'CLUSTER-TWO'}],
            [{'runId': 'second-standalone', 'target': 'Cluster-Three'}],
            [{'runId': 'targetless', 'target': ''}],
        ])
        cutoff = datetime.datetime(
            2024,
            1,
            2,
            3,
            4,
            5,
            tzinfo=datetime.timezone.utc,
        )

        targets = inactive_filter._get_active_targets(
            self._cluster('cluster'),
            cutoff,
        )

        self.assertEqual(
            {'cluster-one', 'cluster-two', 'cluster-three'},
            targets,
        )
        statuses = (
            'NotStarted',
            'Starting',
            'Provisioning',
            'Preparing',
            'Queued',
            'Running',
            'Finalizing',
            'CancelRequested',
            'NotResponding',
            'Unapproved',
            'Pausing',
            'Paused',
        )
        status_filter = ' or '.join(
            f"status eq '{status}'" for status in statuses
        )
        base_url = (
            f'https://westus.api.azureml.ms/history/v1.0{self.parent_id}/'
            'experimentids'
        )
        self.assertEqual(
            [
                call(
                    f'{base_url}/experiment-one/runs:query',
                    {'filter': status_filter},
                ),
                call(
                    f'{base_url}/experiment-one/runs:query',
                    {'filter': 'endTimeUtc ge 2024-01-02T03:04:05Z'},
                ),
                call(
                    f'{base_url}/experiment-two/runs:query',
                    {'filter': status_filter},
                ),
                call(
                    f'{base_url}/experiment-two/runs:query',
                    {'filter': 'endTimeUtc ge 2024-01-02T03:04:05Z'},
                ),
            ],
            inactive_filter._query_history.call_args_list,
        )

    def test_inactive_skips_workspace_without_discovery_url(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._get_active_targets = Mock(return_value=set())
        missing_discovery = self._cluster('missing-discovery')
        missing_discovery.pop('c7n:WorkspaceDiscoveryUrl')
        east_parent_id = self.parent_id.replace(
            'test-workspace',
            'east-workspace',
        )
        idle_east = self._cluster(
            'idle-east',
            parent_id=east_parent_id,
            discovery_url='https://eastus.api.azureml.ms/discovery',
        )

        with self.assertLogs(inactive_filter.log, level='WARNING') as logs:
            resources = inactive_filter.process([
                missing_discovery,
                idle_east,
            ])

        self.assertEqual(['idle-east'], [r['name'] for r in resources])
        self.assertIn(self.parent_id, logs.output[0])
        inactive_filter._get_active_targets.assert_called_once_with(
            idle_east,
            ANY,
        )

    def test_inactive_skips_workspace_on_request_failure(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._get_active_targets = Mock(side_effect=[
            requests.RequestException('Run History unavailable'),
            {'active-east'},
        ])
        east_parent_id = self.parent_id.replace(
            'test-workspace',
            'east-workspace',
        )
        clusters = [
            self._cluster('idle-west'),
            self._cluster(
                'active-east',
                parent_id=east_parent_id,
                discovery_url='https://eastus.api.azureml.ms/discovery',
            ),
            self._cluster(
                'idle-east',
                parent_id=east_parent_id,
                discovery_url='https://eastus.api.azureml.ms/discovery',
            ),
        ]

        with self.assertLogs(inactive_filter.log, level='WARNING') as logs:
            resources = inactive_filter.process(clusters)

        self.assertEqual(['idle-east'], [r['name'] for r in resources])
        self.assertIn(self.parent_id, logs.output[0])

    def test_inactive_workspace_cache(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._get_active_targets = Mock(side_effect=[
            {'active-west'},
            {'active-east'},
        ])
        east_parent_id = self.parent_id.replace(
            'test-workspace',
            'east-workspace',
        )
        clusters = [
            self._cluster('active-west'),
            self._cluster('idle-west'),
            self._cluster(
                'active-east',
                parent_id=east_parent_id,
                discovery_url='https://eastus.api.azureml.ms/discovery',
            ),
        ]

        resources = inactive_filter.process(clusters)

        self.assertEqual(['idle-west'], [r['name'] for r in resources])
        self.assertEqual(2, inactive_filter._get_active_targets.call_count)
        history_calls = inactive_filter._get_active_targets.call_args_list
        self.assertEqual('active-west', history_calls[0].args[0]['name'])
        self.assertEqual('active-east', history_calls[1].args[0]['name'])

    def test_inactive_active_targets_use_separate_workspace_endpoints(self):
        inactive_filter = self._load_inactive_filter()
        inactive_filter._get_experiments = Mock(side_effect=[
            ['west-experiment'],
            ['east-experiment'],
        ])
        inactive_filter._query_history = Mock(side_effect=[
            [{'target': 'west-cluster'}],
            [],
            [{'target': 'east-cluster'}],
            [],
        ])
        cutoff = datetime.datetime(
            2024,
            1,
            2,
            3,
            4,
            5,
            tzinfo=datetime.timezone.utc,
        )
        east_parent_id = self.parent_id.replace(
            'test-workspace',
            'east-workspace',
        )

        west_targets = inactive_filter._get_active_targets(
            self._cluster('west-cluster'),
            cutoff,
        )
        east_targets = inactive_filter._get_active_targets(
            self._cluster(
                'east-cluster',
                parent_id=east_parent_id,
                discovery_url='https://eastus.api.azureml.ms/discovery',
            ),
            cutoff,
        )

        self.assertEqual({'west-cluster'}, west_targets)
        self.assertEqual({'east-cluster'}, east_targets)
        urls = [
            history_call.args[0]
            for history_call in inactive_filter._query_history.call_args_list
        ]
        self.assertTrue(all(
            url.startswith('https://westus.api.azureml.ms/')
            for url in urls[:2]
        ))
        self.assertTrue(all(
            url.startswith('https://eastus.api.azureml.ms/')
            for url in urls[2:]
        ))
