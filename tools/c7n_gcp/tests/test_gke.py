# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from gcp_common import BaseTest, event_data


class KubernetesClusterTest(BaseTest):

    def test_cluster_query(self):
        project_id = "cloud-custodian"

        factory = self.replay_flight_data('gke-cluster-query', project_id)
        p = self.load_policy(
            {'name': 'all-gke-cluster',
             'resource': 'gcp.gke-cluster'},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(resources[0]['status'], 'RUNNING')
        self.assertEqual(resources[0]['name'], 'standard-cluster-1')

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

        p = self.load_policy({
            'name': 'one-gke-cluster',
            'resource': 'gcp.gke-cluster',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['io.k8s.core.v1.nodes.create']}},
            session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('k8s_create_cluster.json')
        clusters = exec_mode.run(event, None)

        self.assertEqual(clusters[0]['name'], name)

    def test_cluster_delete(self):
        project_id = "cloud-custodian"
        resource_name = "custodian-cluster-delete-test"

        factory = self.replay_flight_data('gke-cluster-delete', project_id)
        p = self.load_policy(
            {'name': 'delete-gke-cluster',
             'resource': 'gcp.gke-cluster',
             'filters': [{'name': resource_name}],
             'actions': ['delete']},
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
            {'name': 'all-gke-nodepools',
             'resource': 'gcp.gke-nodepool'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(resources[0]['status'], 'RUNNING')
        self.assertEqual(resources[0]['name'], 'default-pool')

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
