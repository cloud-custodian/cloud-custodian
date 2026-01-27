# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_kube import KubeTest
from c7n.exceptions import PolicyValidationError
from c7n_kube.utils import evaluate_result


class TestAdmissionControllerMode(KubeTest):
    def test_kube_admission_policy(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "test-admission",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "allow",
                    "operations": ["CREATE", "DELETE"],
                },
            },
            session_factory=factory,
        )
        expected = {
            "operations": ["CREATE", "DELETE"],
            "resources": [policy.resource_manager.get_model().plural.lower()],
            "group": "",
            "apiVersions": policy.resource_manager.get_model().version.lower(),
            "scope": "Namespaced" if policy.resource_manager.get_model().namespaced else "Cluster",
        }
        match_values = policy.get_execution_mode().get_match_values()
        self.assertEqual(expected, match_values)
        event = self.get_event("create_pod")
        resources = policy.push(event)
        self.assertEqual(len(resources), 1)
        result = evaluate_result("allow", resources)
        self.assertEqual(result, "allow")

    def test_kube_event_filter(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "test-event-filter",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "deny",
                    "operations": [
                        "CREATE",
                    ],
                },
                "filters": [
                    {
                        "type": "event",
                        "key": "request.userInfo.groups",
                        "value": "system:masters",
                        "op": "in",
                        "value_type": "swap",
                    }
                ],
            },
            session_factory=factory,
        )
        event = self.get_event("create_pod")
        resources = policy.push(event)
        self.assertEqual(len(resources), 1)
        result = evaluate_result("deny", resources)
        self.assertEqual(result, "deny")

    def test_kube_delete_event(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "test-delete-pod",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "deny",
                    "operations": ["DELETE"],
                },
                "filters": [
                    # we should be able to filter on the attribbutes of the resource to be deleted
                    {"metadata.name": "static-web"},
                ],
            },
            session_factory=factory,
        )
        event = self.get_event("delete_pod")
        resources = policy.push(event)
        self.assertTrue(resources)
        result = evaluate_result("deny", resources)
        self.assertEqual(result, "deny")

    def test_admission_warn_event(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "test-warn-pod",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "warn",
                    "operations": ["CREATE"],
                },
            },
            session_factory=factory,
        )
        event = self.get_event("create_pod")
        resources = policy.push(event)
        self.assertTrue(resources)
        result = evaluate_result("warn", resources)
        self.assertEqual(result, "warn")

    def test_admission_warn_event_no_results(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "test-warn-pod",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "warn",
                    "operations": ["CREATE"],
                },
                "filters": [{"foo": "bar"}],
            },
            session_factory=factory,
        )
        event = self.get_event("create_pod")
        resources = policy.push(event)
        self.assertEqual(len(resources), 0)
        result = evaluate_result("warn", resources)
        self.assertEqual(result, "allow")

    def test_admission_allow_crd(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "no-custom-resource-for-you",
                "resource": "k8s.custom-namespaced-resource",
                "query": [
                    {
                        "plural": "policyreports",
                        "group": "wgpolicyk8s.io",
                        "version": "v1alpha2",
                    }
                ],
                "mode": {
                    "type": "k8s-admission",
                    "on-match": "deny",
                    "operations": ["CREATE"],
                },
            },
            session_factory=factory,
        )
        event = self.get_event("create_policyreport")
        resources = policy.push(event)
        self.assertEqual(len(resources), 1)
        result = evaluate_result("deny", resources)
        self.assertEqual(result, "deny")

    def test_admission_action_validate(self):
        factory = self.replay_flight_data()
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    "name": "label-pod",
                    "resource": "k8s.pod",
                    "mode": {
                        "type": "k8s-admission",
                        "on-match": "allow",
                        "operations": ["CREATE"],
                    },
                    "actions": [{"type": "label", "labels": {"foo": "bar"}}],
                },
                session_factory=factory,
            )

    def test_sub_resource_pod_exec(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "test-deny-pod-exec-based-on-group",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "subresource": ["exec"],
                    "on-match": "deny",
                    "operations": ["CONNECT"],
                },
                "filters": [
                    {
                        "not": [
                            {
                                "type": "event",
                                "key": "request.userInfo.groups",
                                "value": "allow-exec",
                                "op": "in",
                                "value_type": "swap",
                            }
                        ]
                    }
                ],
            },
            session_factory=factory,
        )
        event = self.get_event("connect_pod_exec_options")
        resources = policy.push(event)
        self.assertEqual(len(resources), 1)
        result = evaluate_result("deny", resources)
        self.assertEqual(result, "deny")

    def test_sub_resource_pod_attach_exec(self):
        # policy should be able to handle multiple subresources
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                "name": "test-deny-pod-exec-based-on-group",
                "resource": "k8s.pod",
                "mode": {
                    "type": "k8s-admission",
                    "subresource": ["exec", "attach"],
                    "on-match": "deny",
                    "operations": ["CONNECT"],
                },
                "filters": [
                    {
                        "or": [
                            {
                                "type": "event",
                                "key": "request.userInfo.groups",
                                "value": "allow-exec",
                                "op": "not-in",
                                "value_type": "swap",
                            }
                        ]
                    }
                ],
            },
            session_factory=factory,
        )
        event = self.get_event("connect_pod_attach_options")
        resources = policy.push(event)
        self.assertEqual(len(resources), 1)
        result = evaluate_result("deny", resources)
        self.assertEqual(result, "deny")
