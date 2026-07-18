from gcp_common import BaseTest


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
