# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_kube import KubeTest


class ClusterRoleBindingTest(KubeTest):
    def test_cluster_role_binding_query(self):
        factory = self.replay_flight_data()
        # factory = self.record_flight_data()
        p = self.load_policy(
            {"name": "cluster-role-bindings", "resource": "k8s.cluster-role-binding"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        sorted_resources = sorted([r["metadata"]["name"] for r in resources])
        assert "cluster-admin" in sorted_resources
        assert "cert-manager-cainjector" in sorted_resources
        assert "system:controller:token-cleaner" in sorted_resources

    def test_cluster_role_binding_role_ref_filter(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "cluster-role-bindings-wildcard",
                "resource": "k8s.cluster-role-binding",
                "filters": [
                    {
                        "type": "role-ref",
                        "key": "length(rules[?resources && contains(resources, '*')])",
                        "op": "gt",
                        "value": 0,
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["metadata"]["name"], "cluster-admin")
        self.assertEqual(resources[0]["c7n:role-ref"]["metadata"]["name"], "cluster-admin")


class RoleBindingTest(KubeTest):
    def test_role_binding_query(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {"name": "role-bindings", "resource": "k8s.role-binding"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        sorted_resources = sorted([r["metadata"]["name"] for r in resources])
        assert "cert-manager-cainjector:leaderelection" in sorted_resources
        assert "system::leader-locking-kube-controller-manager" in sorted_resources
        assert "cert-manager-webhook:dynamic-serving" in sorted_resources

    def test_role_binding_role_ref_filter(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "role-bindings-wildcard",
                "resource": "k8s.role-binding",
                "filters": [
                    {
                        "type": "role-ref",
                        "key": "length(rules[?resources && contains(resources, '*')])",
                        "op": "gt",
                        "value": 0,
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["metadata"]["name"], "wildcard-binding")
        self.assertEqual(resources[0]["c7n:role-ref"]["metadata"]["name"], "wildcard-role")
