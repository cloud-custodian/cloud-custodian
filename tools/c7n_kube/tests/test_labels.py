# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_kube import KubeTest

from c7n_kube.utils import evaluate_result


class TestLabelAction(KubeTest):
    def test_label_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "label-namespace",
                "resource": "k8s.namespace",
                "filters": [{"metadata.labels": None}, {"metadata.name": "test"}],
                "actions": [{"type": "label", "labels": {"test": "value"}}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertTrue(resources)
        client = factory().client(group="Core", version="V1")
        resources = client.list_namespace().to_dict()["items"]
        test_namespace = [r for r in resources if r["metadata"]["name"] == "test"]
        self.assertEqual(len(test_namespace), 1)
        labels = test_namespace[0]["metadata"]["labels"]
        self.assertEqual(labels, {"test": "value"})

    def test_namespaced_label_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "label-service",
                "resource": "k8s.service",
                "filters": [
                    {"metadata.labels.test": "absent"},
                    {"metadata.name": "hello-node"},
                ],
                "actions": [{"type": "label", "labels": {"test": "value"}}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertTrue(resources)
        client = factory().client(group="Core", version="V1")
        resources = client.list_service_for_all_namespaces().to_dict()["items"]
        test_namespace = [r for r in resources if r["metadata"]["name"] == "hello-node"]
        self.assertEqual(len(test_namespace), 1)
        labels = test_namespace[0]["metadata"]["labels"]
        self.assertTrue("test" in labels.keys())
        self.assertEqual(labels["test"], "value")


class TestKubeEventLabelAction(KubeTest):
    def test_event_label_no_labels(self):
        factory = self.replay_flight_data()
        event = self.get_event("create_pod_no_labels")
        policy = self.load_policy(
            {
                "name": "test-label-no-labels",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "warn",
                    "operations": ["CREATE"],
                },
                "filters": [{"type": "value", "key": "metadata.labels", "value": "absent"}],
                "actions": [{"type": "event-label", "labels": {"foo": "bar"}}],
            },
            session_factory=factory,
        )
        resources = policy.push(event)
        result = evaluate_result("warn", resources)
        self.assertEqual(result, "warn")
        self.assertEqual(len(resources), 1)
        resources[0]["c7n:patches"]
        self.assertEqual(
            resources[0]["c7n:patches"][0],
            {"op": "add", "path": "/metadata/labels", "value": {"foo": "bar"}},
        )

    def test_admission_event_auto_label_user(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "label-pod",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "allow",
                    "operations": ["CREATE"],
                },
                "actions": [
                    {
                        "type": "auto-label-user",
                    }
                ],
            },
            session_factory=factory,
        )
        event = self.get_event("create_pod")
        resources = policy.push(event)
        result = evaluate_result("allow", resources)
        self.assertEqual(result, "allow")
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]["c7n:patches"]), 1)
        self.assertEqual(
            resources[0]["c7n:patches"],
            [
                {
                    "op": "add",
                    "path": "/metadata/labels/OwnerContact",
                    "value": "kubernetes-admin",
                }
            ],
        )

    def test_admission_event_label(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "label-pod",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "allow",
                    "operations": ["CREATE"],
                },
                "actions": [
                    {
                        "type": "event-label",
                        "labels": {
                            "foo": "bar",
                            "role": "different role",
                            "test": None,
                        },
                    }
                ],
            },
            session_factory=factory,
        )
        event = self.get_event("create_pod")
        resources = policy.push(event)
        result = evaluate_result("allow", resources)
        self.assertEqual(result, "allow")
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]["c7n:patches"]), 3)
        self.assertEqual(
            resources[0]["c7n:patches"],
            [
                {"op": "remove", "path": "/metadata/labels/test"},
                {"op": "add", "path": "/metadata/labels/foo", "value": "bar"},
                {
                    "op": "replace",
                    "path": "/metadata/labels/role",
                    "value": "different role",
                },
            ],
        )
