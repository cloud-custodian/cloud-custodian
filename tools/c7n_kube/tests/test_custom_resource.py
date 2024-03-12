# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#

from c7n.exceptions import PolicyValidationError

from common_kube import KubeTest


class TestCustomResource(KubeTest):
    def test_custom_cluster_resource_query(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "custom-resources",
                "resource": "k8s.custom-cluster-resource",
                "query": [
                    {
                        "group": "stable.example.com",
                        "version": "v1",
                        "plural": "crontabscluster",
                    }
                ],
            },
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["apiVersion"], "stable.example.com/v1")
        self.assertEqual(resources[0]["kind"], "CronTabCluster")

    def test_custom_namespaced_resource_query(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "custom-resources",
                "resource": "k8s.custom-namespaced-resource",
                "query": [
                    {
                        "group": "stable.example.com",
                        "version": "v1",
                        "plural": "crontabs",
                    }
                ],
            },
            session_factory=factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["apiVersion"], "stable.example.com/v1")
        self.assertEqual(resources[0]["kind"], "CronTab")

    def test_custom_resource_validation(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "custom-resources",
                "resource": "k8s.custom-namespaced-resource",
            },
            validate=True,
        )

        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "custom-resources",
                "resource": "k8s.custom-namespaced-resource",
                "query": [{"bad": "value"}],
            },
            validate=True,
        )
