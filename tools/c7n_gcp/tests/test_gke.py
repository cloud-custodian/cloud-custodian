# Copyright 2019 Capital One Services, LLC
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
