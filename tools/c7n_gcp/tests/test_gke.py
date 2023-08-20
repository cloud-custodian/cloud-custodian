# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from gcp_common import BaseTest, event_data
from c7n.config import Config

class KubernetesClusterTest(BaseTest):

    def test_cluster_query(self):
        project_id = "cloud-custodian"

        factory = self.replay_flight_data('gke-cluster-query', project_id)
        p = self.load_policy(
            {
                'name': 'all-gke-cluster',
                'resource': 'gcp.gke-cluster'
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(resources[0]['status'], 'RUNNING')
        self.assertEqual(resources[0]['name'], 'standard-cluster-1')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:container:us-central1-a:cloud-custodian:cluster/standard-cluster-1'
            ],
        )

    def test_gke_cluster_tags(self):
        project_id = "cloud-custodian"
        factory = self.replay_flight_data("gke-cluster-query-resourceLabels", project_id)
        p = self.load_policy(
            {
                'name': 'all-gke-cluster',
                'resource': 'gcp.gke-cluster',
                'filters': [{"tag:foo": "bar"}]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(resources[0]['name'], 'cluster-1')
        self.assertEqual(resources[0]['resourceLabels']['foo'], 'bar')

    def test_cluster_get(self):
        project_id = "cloud-custodian"
        name = "standard-cluster-1"

        factory = self.replay_flight_data('gke-cluster-get', project_id)

        p = self.load_policy(
            {
                'name': 'one-gke-cluster',
                'resource': 'gcp.gke-cluster',
                'mode': {
                    'type': 'gcp-audit',
                    'methods': ['io.k8s.core.v1.nodes.create']
                }
            },
            session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('k8s_create_cluster.json')
        clusters = exec_mode.run(event, None)

        self.assertEqual(clusters[0]['name'], name)
        self.assertEqual(
            p.resource_manager.get_urns(clusters),
            [
                'gcp:container:us-central1-a:cloud-custodian:cluster/standard-cluster-1'
            ],
        )

    def test_cluster_set_labels(self):
        project_id = 'elastic-platform-capacity'
        name = "standard-cluster-1"
        factory = self.replay_flight_data('gke-cluster-set-label', project_id)
        p = self.load_policy(
            {
                'name': 'label-gke-cluster-cache',
                'resource': 'gcp.gke-cluster',
                'filters': [{'name': name}],
                'actions': [{'type': 'set-labels',
                            'labels': {'test_label': 'new_value'}}]},
            cache=True,
            config=Config.empty(
                cache='memory',
                cache_period=10,
                output_dir=self.get_temp_dir(),
            ),
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        p = self.load_policy(
            {
                'name': 'label-gke-cluster',
                'resource': 'gcp.gke-cluster',
                'filters': [{'name': name}],
                'actions': [{'type': 'set-labels',
                            'labels': {'test_label': 'test_value'}}]},
            cache=True,
            config=Config.empty(
                cache='memory',
                cache_period=10,
                output_dir=self.get_temp_dir(),
            ),
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {
                        'parent': 'projects/{}/locations/{}'.format(
                            project_id,
                            resources[0]['zone'])
                    }),
        self.assertEqual(result[0]['clusters'][0]['resourceLabels']['test_label'], 'test_value')

    def test_cluster_remove_labels(self):
        project_id = 'cloud-custodian'
        name = "standard-cluster-1"
        factory = self.replay_flight_data('gke-cluster-remove-label', project_id)
        p = self.load_policy(
            {
                'name': 'unlabel-gke-cluster',
                'resource': 'gcp.gke-cluster',
                'filters': [{'name': name}],
                'actions': [{'type': 'set-labels',
                            'remove': ['test_label']}]},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {
                        'parent': 'projects/{}/locations/{}'.format(
                            project_id,
                            resources[0]['zone'])
                    })
        self.assertEqual(result['clusters'][0]['resourceLabels'].get('test_label'), None)

    def test_cluster_delete(self):
        project_id = "cloud-custodian"
        resource_name = "custodian-cluster-delete-test"

        factory = self.replay_flight_data('gke-cluster-delete', project_id)
        p = self.load_policy(
            {
                'name': 'delete-gke-cluster',
                'resource': 'gcp.gke-cluster',
                'filters': [{'name': resource_name}],
                'actions': ['delete']
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(3)

        client = p.resource_manager.get_client()
        result = client.execute_query(
            'list', {'parent': 'projects/{}/locations/{}'.format(
                project_id,
                'us-east1-b')})

        self.assertEqual(result['clusters'][0]['status'], 'STOPPING')



class KubernetesClusterNodePoolTest(BaseTest):

    def test_cluster_node_pools_query(self):
        project_id = "cloud-custodian"

        factory = self.replay_flight_data('gke-cluster-nodepool-query', project_id)

        p = self.load_policy(
            {
                'name': 'all-gke-nodepools',
                'resource': 'gcp.gke-nodepool'
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(resources[0]['status'], 'RUNNING')
        self.assertEqual(resources[0]['name'], 'default-pool')
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                'gcp:container:us-central1-a:cloud-custodian:cluster-node-pool/default-pool'
            ],
        )

    def test_cluster_node_pools_get(self):

        project_id = "cloud-custodian"
        name = "pool-1"

        factory = self.replay_flight_data('gke-cluster-nodepool-get', project_id)

        p = self.load_policy(
            {
                'name': 'one-gke-nodepool',
                'resource': 'gcp.gke-nodepool',
                'mode': {
                    'type': 'gcp-audit',
                    'methods': ['io.k8s.core.v1.pods.create']
                }
            }, session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('k8s_create_pool.json')
        pools = exec_mode.run(event, None)

        self.assertEqual(pools[0]['name'], name)
        self.assertEqual(
            p.resource_manager.get_urns(pools),
            [
                'gcp:container:us-central1-a:cloud-custodian:cluster-node-pool/pool-1'
            ],
        )
