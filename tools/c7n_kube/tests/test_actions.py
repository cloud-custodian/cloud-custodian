# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from common_kube import KubeTest


class TestDeleteAction(KubeTest):
    def test_delete_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "delete-namespace",
                "resource": "k8s.namespace",
                "filters": [{"metadata.name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("Core", "V1")
        namespaces = client.list_namespace().to_dict()["items"]
        test_namespace = [n for n in namespaces if n["metadata"]["name"] == "test"][0]
        self.assertEqual(test_namespace["status"]["phase"], "Terminating")

    def test_delete_namespaced_resource(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "delete-service",
                "resource": "k8s.service",
                "filters": [{"metadata.name": "hello-node"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("Core", "V1")
        namespaces = client.list_service_for_all_namespaces().to_dict()["items"]
        hello_node_service = [n for n in namespaces if n["metadata"]["name"] == "hello-node"]
        self.assertFalse(hello_node_service)


class TestPatchAction(KubeTest):
    def test_patch_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "test-patch",
                "resource": "k8s.deployment",
                "filters": [{"metadata.name": "hello-node"}, {"spec.replicas": 1}],
                "actions": [{"type": "patch", "options": {"spec": {"replicas": 2}}}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("Apps", "V1")
        deployments = client.list_deployment_for_all_namespaces().to_dict()["items"]
        hello_node_deployment = [d for d in deployments if d["metadata"]["name"] == "hello-node"][0]
        self.assertEqual(hello_node_deployment["spec"]["replicas"], 2)
