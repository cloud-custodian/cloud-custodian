from gcp_common import BaseTest
from c7n.exceptions import PolicyValidationError
from c7n.testing import C7N_FUNCTIONAL
from c7n_gcp.client import get_default_project


class ArtifactRegistryRepositoryTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('artifactregistry-repositories-query')
        p = self.load_policy({
            'name': 'artifact',
            'resource': 'gcp.artifact-repository'},
            config={'region': 'us-central1'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/'
                                               'locations/us-central1/repositories/test')

    def test_artifact_repository_label(self):
        # Set the 'env' label to not the default
        factory = self.replay_flight_data('artifact-repository-label')
        repo_name = ('projects/cloud-custodian/locations/us-central1/'
                     'repositories/c7n-artifact-repo')
        p = self.load_policy(
            {
                'name': 'artifact-repository-label',
                'resource': 'gcp.artifact-repository',
                'filters': [{
                    'type': 'value',
                    'key': 'name',
                    'value': repo_name,
                }],
                'actions': [
                    {'type': 'set-labels',
                     'labels': {'env': 'production'}}
                ]
            },
            config={'region': 'us-central1'},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['labels']['env'], 'default')

        # Fetch the repository manually to confirm the label was changed
        client = p.resource_manager.get_client()
        result = client.execute_query(
            'get',
            {'name': repo_name}
        )
        self.assertEqual(result['labels']['env'], 'production')

    def test_artifact_repository_cleanup_policy_validation(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy({
                'name': 'artifact-repository-cleanup-policy-invalid',
                'resource': 'gcp.artifact-repository',
                'actions': [
                    {'type': 'set-cleanup-policy'}
                ]
            }, config={'region': 'us-central1'})

    def test_artifact_repository_set_cleanup_policy(self):
        """Test setting Artifact Registry cleanup policy."""
        flight_name = 'artifact-repository-set-cleanup-policy'
        location = 'us-central1'

        if C7N_FUNCTIONAL:
            functional_project_id = get_default_project()
            session_factory = self.record_flight_data(
                flight_name, project_id=functional_project_id)
        else:
            session_factory = self.replay_flight_data(flight_name)

        policy = self.load_policy(
            {
                'name': 'artifact-repository-set-cleanup-policy',
                'resource': 'gcp.artifact-repository',
                'actions': [{
                    'type': 'set-cleanup-policy',
                    'cleanup-policies': {
                        'delete-old': {
                            'id': 'delete-old',
                            'action': 'DELETE',
                            'condition': {
                                'olderThan': '2592000s'
                            }
                        }
                    }
                }]
            },
            config={'region': location},
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = policy.resource_manager.get_client()
        repository = client.execute_query('get', {'name': resources[0]['name']})
        self.assertIn('delete-old', repository.get('cleanupPolicies', {}))
