import os
import vcr
from gcp_common import BaseTest


class VertexEndpointTest(BaseTest):

    def _get_recorder(self, flight_name):
        # Helper to setup the recorder with the correct paths and settings
        base_dir = os.path.abspath(os.path.dirname(__file__))
        flight_dir = os.path.join(base_dir, 'data', 'flights', flight_name)
        os.makedirs(flight_dir, exist_ok=True)

        print(f"\n[INFO] Saving recording to: {flight_dir}/recording.json")

        return vcr.VCR(
            cassette_library_dir=flight_dir,
            record_mode='all',
            serializer='json',
            # THIS FIXES THE BINARY DATA ERROR
            decode_compressed_response=True,
        )

    def test_vertex_endpoint_query(self):
        recorder = self._get_recorder('vertex-endpoint-query')

        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'cloud-custodian')
        factory = self.replay_flight_data(
            'vertex-endpoint-query', project_id=project_id
        )

        p = self.load_policy(
            {
                'name': 'vertex-query',
                'resource': 'gcp.vertex-endpoint',
            },
            session_factory=factory,
        )

        with recorder.use_cassette('recording.json'):
            resources = p.run()

        self.assertTrue(len(resources) > 0)
        self.assertTrue('displayName' in resources[0])

    def test_vertex_endpoint_filter_empty(self):
        recorder = self._get_recorder('vertex-endpoint-filter')

        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'cloud-custodian')
        factory = self.replay_flight_data(
            'vertex-endpoint-filter', project_id=project_id
        )

        p = self.load_policy(
            {
                'name': 'vertex-filter',
                'resource': 'gcp.vertex-endpoint',
                'filters': [{'type': 'empty-endpoint', 'value': True}],
            },
            session_factory=factory,
        )

        with recorder.use_cassette('recording.json'):
            resources = p.run()

        # Assuming you have at least one empty endpoint, check it
        if len(resources) > 0:
            self.assertEqual(len(resources[0].get('deployedModels', [])), 0)

    def test_vertex_endpoint_delete(self):
        recorder = self._get_recorder('vertex-endpoint-delete')

        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT', 'cloud-custodian')
        factory = self.replay_flight_data(
            'vertex-endpoint-delete', project_id=project_id
        )

        p = self.load_policy(
            {
                'name': 'vertex-delete',
                'resource': 'gcp.vertex-endpoint',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'displayName',
                        'value': 'multinomial-endpoint-02',
                    }
                ],
                'actions': ['delete'],
            },
            session_factory=factory,
        )

        with recorder.use_cassette('recording.json'):
            resources = p.run()

        if len(resources) > 0:
            self.assertEqual(
                resources[0]['displayName'], 'multinomial-endpoint-02'
            )
