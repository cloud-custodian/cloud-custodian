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
