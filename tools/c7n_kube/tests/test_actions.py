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

    def test_enhanced_patch_schema_validation(self):
        """Test that enhanced patch action schema validates correctly"""
        from c7n_kube.actions.core import PatchResource

        # Test that save-options-tag and restore-options-tag are in schema
        schema = PatchResource.schema
        self.assertEqual(schema['type'], 'object')
        self.assertEqual(schema['properties']['type']['enum'], ['patch'])
        self.assertIn('save-options-tag', schema['properties'])
        self.assertIn('restore-options-tag', schema['properties'])
        self.assertEqual(schema['properties']['save-options-tag']['type'], 'string')
        self.assertEqual(schema['properties']['restore-options-tag']['type'], 'string')

    def test_patch_resource_save_restore_logic(self):
        """Test save/restore logic without requiring Kubernetes API calls"""
        from c7n_kube.actions.core import PatchResource
        from unittest.mock import Mock

        # Mock manager and model
        manager = Mock()
        manager.get_model.return_value.namespaced = True
        manager.get_model.return_value.patch = 'patch_namespaced_deployment'

        # Test save functionality
        save_action = PatchResource(
            {'save-options-tag': 'test-save-tag', 'options': {'spec': {'replicas': 0}}}, manager
        )

        # Mock client and resources
        mock_client = Mock()
        mock_patch_op = Mock()
        setattr(mock_client, 'patch_namespaced_deployment', mock_patch_op)

        resources = [
            {
                'metadata': {
                    'name': 'test-deployment',
                    'namespace': 'default',
                    'labels': {'existing': 'label'},
                },
                'spec': {'replicas': 3},
            }
        ]

        # Test save functionality - should call patch_resources_replicas
        save_action.patch_resources_replicas = Mock()
        save_action.process_resource_set(mock_client, resources)

        # Verify save logic was called
        save_action.patch_resources_replicas.assert_called_once()
        call_args = save_action.patch_resources_replicas.call_args
        patch_data = call_args[0][2]  # Third argument is the patch dict

        # Verify save tag was added to labels
        self.assertIn('test-deployment', patch_data)
        patch_body = patch_data['test-deployment']['body']
        self.assertIn('metadata', patch_body)
        self.assertIn('labels', patch_body['metadata'])
        self.assertEqual(patch_body['metadata']['labels']['test-save-tag'], 'replicas-3')

        # Test restore functionality
        restore_action = PatchResource({'restore-options-tag': 'test-restore-tag'}, manager)

        resources_with_saved_data = [
            {
                'metadata': {
                    'name': 'test-deployment-2',
                    'namespace': 'default',
                    'labels': {'test-restore-tag': 'replicas-5'},
                },
                'spec': {'replicas': 0},
            }
        ]

        restore_action.patch_resources_replicas = Mock()
        restore_action.process_resource_set(mock_client, resources_with_saved_data)

        # Verify restore logic was called
        restore_action.patch_resources_replicas.assert_called_once()
        call_args = restore_action.patch_resources_replicas.call_args
        patch_data = call_args[0][2]  # Third argument is the patch dict

        # Verify restore logic set correct replica count
        self.assertIn('test-deployment-2', patch_data)
        patch_body = patch_data['test-deployment-2']['body']
        self.assertEqual(patch_body['spec']['replicas'], 5)

    def test_patch_resource_edge_cases(self):
        """Test edge cases and error paths for better coverage"""
        from c7n_kube.actions.core import PatchResource
        from unittest.mock import Mock
        from kubernetes.client.exceptions import ApiException

        # Mock manager and model
        manager = Mock()
        manager.get_model.return_value.namespaced = True
        manager.get_model.return_value.patch = 'patch_namespaced_deployment'

        # Test 1: Resource with no labels (None case)
        save_action = PatchResource(
            {'save-options-tag': 'test-save-tag', 'options': {'spec': {'replicas': 0}}}, manager
        )

        resources_no_labels = [
            {
                'metadata': {
                    'name': 'test-deployment-no-labels',
                    'namespace': 'default',
                    'labels': None,  # This should trigger the None check
                },
                'spec': {'replicas': 2},
            }
        ]

        # Mock the patch_resources_replicas to capture the call
        save_action.patch_resources_replicas = Mock()
        save_action.process_resource_set(Mock(), resources_no_labels)

        # Verify labels were created and save tag was added
        call_args = save_action.patch_resources_replicas.call_args
        patch_data = call_args[0][2]
        patch_body = patch_data['test-deployment-no-labels']['body']
        self.assertEqual(patch_body['metadata']['labels']['test-save-tag'], 'replicas-2')

        # Test 2: Restore with missing restore tag (should not restore)
        restore_action = PatchResource({'restore-options-tag': 'missing-tag'}, manager)

        resources_missing_tag = [
            {
                'metadata': {
                    'name': 'test-deployment-missing-tag',
                    'namespace': 'default',
                    'labels': {'other-tag': 'other-value'},  # No restore tag
                },
                'spec': {'replicas': 0},
            }
        ]

        restore_action.patch_resources_replicas = Mock()
        restore_action.process_resource_set(Mock(), resources_missing_tag)

        # Should still call patch_resources_replicas but without spec changes
        call_args = restore_action.patch_resources_replicas.call_args
        patch_data = call_args[0][2]
        patch_body = patch_data['test-deployment-missing-tag']['body']
        # Should not have spec.replicas since restore tag was missing
        self.assertNotIn('spec', patch_body)

        # Test 3: 404 error handling in patch_resources_replicas
        error_action = PatchResource({'options': {'spec': {'replicas': 1}}}, manager)

        mock_client_404 = Mock()
        mock_patch_op_404 = Mock()
        mock_patch_op_404.side_effect = ApiException(status=404, reason="Not Found")
        setattr(mock_client_404, 'patch_namespaced_deployment', mock_patch_op_404)

        resources_404 = [
            {'metadata': {'name': 'test-404', 'namespace': 'default'}, 'spec': {'replicas': 1}}
        ]

        # This should not raise an exception but log a warning
        try:
            error_action.patch_resources_replicas(
                mock_client_404, resources_404, {'test-404': {'body': {'spec': {'replicas': 1}}}}
            )
        except ApiException:
            self.fail("ApiException with 404 status should be handled gracefully")

        # Test 4: Non-404 ApiException should be re-raised
        mock_client_500 = Mock()
        mock_patch_op_500 = Mock()
        mock_patch_op_500.side_effect = ApiException(status=500, reason="Server Error")
        setattr(mock_client_500, 'patch_namespaced_deployment', mock_patch_op_500)

        resources_500 = [
            {'metadata': {'name': 'test-500', 'namespace': 'default'}, 'spec': {'replicas': 1}}
        ]

        with self.assertRaises(ApiException):
            error_action.patch_resources_replicas(
                mock_client_500, resources_500, {'test-500': {'body': {'spec': {'replicas': 1}}}}
            )

    def test_patch_resource_register_resources(self):
        """Test the register_resources class method"""
        from c7n_kube.actions.core import PatchResource
        from unittest.mock import Mock

        # Mock registry and resource_class
        registry = Mock()
        resource_class = Mock()

        # Test successful registration
        model = Mock()
        model.patch = 'patch_namespaced_deployment'
        model.namespaced = True
        resource_class.resource_type = model
        resource_class.action_registry = Mock()

        PatchResource.register_resources(registry, resource_class)

        # Should call register with 'patch' and PatchResource
        resource_class.action_registry.register.assert_called_once_with('patch', PatchResource)

        # Test registration skipped when model lacks patch attribute
        model_no_patch = Mock()
        del model_no_patch.patch  # Remove patch attribute
        resource_class.resource_type = model_no_patch
        resource_class.action_registry.reset_mock()

        PatchResource.register_resources(registry, resource_class)

        # Should not call register
        resource_class.action_registry.register.assert_not_called()
