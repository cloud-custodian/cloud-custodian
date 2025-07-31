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

    def test_patch_action_handles_404_gracefully(self):
        """Test that 404 errors are handled gracefully during patch operations"""
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "test-patch-missing-resource",
                "resource": "k8s.deployment",
                "filters": [{"metadata.name": "non-existent-deployment"}],
                "actions": [{"type": "patch", "options": {"spec": {"replicas": 1}}}],
            },
            session_factory=factory,
        )
        # Should not raise exception even if resource doesn't exist
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_save_options_tag_stores_replica_count(self):
        """Test that save-options-tag correctly stores current replica count in labels"""
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "test-save-replicas",
                "resource": "k8s.deployment",
                "filters": [{"metadata.name": "hello-node"}, {"spec.replicas": 3}],
                "actions": [
                    {
                        "type": "patch",
                        "save-options-tag": "custodian-original-replicas",
                        "options": {"spec": {"replicas": 0}}
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        
        client = factory().client("Apps", "V1")
        deployments = client.list_deployment_for_all_namespaces().to_dict()["items"]
        hello_node_deployment = [d for d in deployments if d["metadata"]["name"] == "hello-node"][0]
        
        # Check that replica count was scaled to 0
        self.assertEqual(hello_node_deployment["spec"]["replicas"], 0)
        
        # Check that original replica count was saved in labels
        labels = hello_node_deployment["metadata"].get("labels", {})
        self.assertIn("custodian-original-replicas", labels)
        self.assertEqual(labels["custodian-original-replicas"], "replicas-3")

    def test_restore_options_tag_restores_replica_count(self):
        """Test that restore-options-tag correctly restores saved replica count"""
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "test-restore-replicas",
                "resource": "k8s.deployment",
                "filters": [
                    {"metadata.name": "hello-node-with-saved-replicas"},
                    {"metadata.labels.custodian-original-replicas": "replicas-5"}
                ],
                "actions": [
                    {
                        "type": "patch",
                        "restore-options-tag": "custodian-original-replicas"
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        
        client = factory().client("Apps", "V1")
        deployments = client.list_deployment_for_all_namespaces().to_dict()["items"]
        restored_deployment = [d for d in deployments if d["metadata"]["name"] == "hello-node-with-saved-replicas"][0]
        
        # Check that replica count was restored to original value
        self.assertEqual(restored_deployment["spec"]["replicas"], 5)

    def test_save_restore_tag_roundtrip(self):
        """Test complete save -> scale down -> restore cycle"""
        factory = self.replay_flight_data()
        
        # Step 1: Save original replicas and scale down
        save_policy = self.load_policy(
            {
                "name": "save-and-scale-down",
                "resource": "k8s.deployment",
                "filters": [{"metadata.name": "test-deployment"}, {"spec.replicas": 4}],
                "actions": [
                    {
                        "type": "patch",
                        "save-options-tag": "custodian-saved-replicas",
                        "options": {"spec": {"replicas": 0}}
                    }
                ],
            },
            session_factory=factory,
        )
        save_resources = save_policy.run()
        self.assertEqual(len(save_resources), 1)
        
        # Step 2: Restore original replicas
        restore_policy = self.load_policy(
            {
                "name": "restore-original-scale",
                "resource": "k8s.deployment",
                "filters": [
                    {"metadata.name": "test-deployment"},
                    {"metadata.labels.custodian-saved-replicas": "replicas-4"}
                ],
                "actions": [
                    {
                        "type": "patch",
                        "restore-options-tag": "custodian-saved-replicas"
                    }
                ],
            },
            session_factory=factory,
        )
        restore_resources = restore_policy.run()
        self.assertEqual(len(restore_resources), 1)
        
        client = factory().client("Apps", "V1")
        deployments = client.list_deployment_for_all_namespaces().to_dict()["items"]
        final_deployment = [d for d in deployments if d["metadata"]["name"] == "test-deployment"][0]
        
        # Verify the roundtrip worked: 4 -> 0 -> 4
        self.assertEqual(final_deployment["spec"]["replicas"], 4)

    def test_restore_tag_ignores_missing_label(self):
        """Test restore gracefully handles missing restore tag"""
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "test-restore-missing-tag",
                "resource": "k8s.deployment",
                "filters": [{"metadata.name": "deployment-without-saved-replicas"}],
                "actions": [
                    {
                        "type": "patch",
                        "restore-options-tag": "non-existent-tag"
                    }
                ],
            },
            session_factory=factory,
        )
        # Should not fail even if restore tag doesn't exist
        resources = p.run()
        # Resource should still be processed, but no actual patch applied
        self.assertEqual(len(resources), 1)

    def test_patch_action_handles_missing_metadata_labels(self):
        """Test that patch action creates labels section when it doesn't exist"""
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "test-patch-no-labels",
                "resource": "k8s.deployment",
                "filters": [{"metadata.name": "deployment-no-labels"}],
                "actions": [
                    {
                        "type": "patch",
                        "save-options-tag": "custodian-test-replicas",
                        "options": {"spec": {"replicas": 1}}
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        
        client = factory().client("Apps", "V1")
        deployments = client.list_deployment_for_all_namespaces().to_dict()["items"]
        deployment = [d for d in deployments if d["metadata"]["name"] == "deployment-no-labels"][0]
        
        # Verify labels section was created and tag was added
        labels = deployment["metadata"].get("labels", {})
        self.assertIn("custodian-test-replicas", labels)

    def test_patch_resources_replicas_batch_operations(self):
        """Test patch_resources_replicas handles multiple resources correctly"""
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "test-batch-patch",
                "resource": "k8s.deployment",
                "filters": [
                    {"or": [
                        {"metadata.name": "deployment-1"},
                        {"metadata.name": "deployment-2"}
                    ]}
                ],
                "actions": [
                    {
                        "type": "patch",
                        "save-options-tag": "batch-test-replicas",
                        "options": {"spec": {"replicas": 0}}
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        
        client = factory().client("Apps", "V1")
        deployments = client.list_deployment_for_all_namespaces().to_dict()["items"]
        
        # Verify both deployments were processed
        deployment_names = [d["metadata"]["name"] for d in deployments if d["metadata"]["name"] in ["deployment-1", "deployment-2"]]
        self.assertEqual(len(deployment_names), 2)
        
        # Verify both have saved replica tags
        for deployment in deployments:
            if deployment["metadata"]["name"] in ["deployment-1", "deployment-2"]:
                labels = deployment["metadata"].get("labels", {})
                self.assertIn("batch-test-replicas", labels)
