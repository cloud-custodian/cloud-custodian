# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class GCPSecretTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('gcp-secret-query')
        p = self.load_policy({
            'name': 'gcp-apikeys',
            'resource': 'gcp.secret'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/'
                                               'secrets/defectdojo_token')
