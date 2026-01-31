# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class VertexEndpointTest(BaseTest):

    @property
    def vcr_config(self):
        return {'match_on': ['method', 'path']}

    def test_vertex_endpoint_query(self):
        # FORCE the project_id to match the recording.json
        factory = self.replay_flight_data(
            "vertex-endpoint-query", project_id="custodian-1291"
        )
        p = self.load_policy(
            {
                'name': 'vertex-query',
                'resource': 'gcp.vertex-endpoint',
            },
            session_factory=factory,
            config={'region': 'us-east-1'},
        )
        resources = p.run()
        self.assertTrue(len(resources) > 0)
        self.assertTrue('displayName' in resources[0])

    def test_vertex_endpoint_filter_empty(self):
        # FORCE the project_id to match the recording.json
        factory = self.replay_flight_data(
            "vertex-endpoint-filter", project_id="custodian-1291"
        )
        p = self.load_policy(
            {
                'name': 'vertex-filter',
                'resource': 'gcp.vertex-endpoint',
                'filters': [{'type': 'empty-endpoint', 'value': True}],
            },
            session_factory=factory,
            config={'region': 'us-east-1'},
        )
        resources = p.run()
        self.assertTrue(len(resources) > 0)
        self.assertEqual(len(resources[0].get('deployedModels', [])), 0)

    def test_vertex_endpoint_delete(self):
        # FORCE the project_id to match the recording.json
        factory = self.replay_flight_data(
            "vertex-endpoint-delete", project_id="custodian-1291"
        )
        p = self.load_policy(
            {
                'name': 'vertex-delete',
                'resource': 'gcp.vertex-endpoint',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'displayName',
                        'value': 'delete-me',
                    }
                ],
                'actions': ['delete'],
            },
            session_factory=factory,
            config={'region': 'us-east-1'},
        )
        resources = p.run()
        self.assertTrue(len(resources) > 0)
        self.assertEqual(resources[0]['displayName'], 'delete-me')
