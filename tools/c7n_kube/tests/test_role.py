# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_kube import KubeTest


class ClusterRoleTest(KubeTest):
    def test_cluster_role_query(self):
        factory = self.replay_flight_data()
        # factory = self.record_flight_data()
        p = self.load_policy(
            {"name": "cluster-roles", "resource": "k8s.cluster-role"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 78)
        sorted_resources = sorted([r["metadata"]["name"] for r in resources])
        assert "cert-manager-cainjector" in sorted_resources
        assert "cluster-admin" in sorted_resources


class RoleTest(KubeTest):
    def test_cluster_role_query(self):
        factory = self.replay_flight_data()
        p = self.load_policy({"name": "role", "resource": "k8s.role"}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 14)
        sorted_resources = sorted([r["metadata"]["name"] for r in resources])
        assert "cert-manager:leaderelection" in sorted_resources
        assert "system:controller:token-cleaner" in sorted_resources
