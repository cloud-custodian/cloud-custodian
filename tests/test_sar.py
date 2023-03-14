# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from .common import BaseTest


class SARTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('test_sar_query_app')
        p = self.load_policy({
            'name': 'test-sar',
            'resource': 'aws.serverless-app'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'GitterArchive')

    def test_cross_account(self):
        factory = self.replay_flight_data('test_sar_cross_account')
        p = self.load_policy({
            'name': 'test-sar',
            'resource': 'aws.serverless-app',
            'filters': [{
                'type': 'cross-account',
                'whitelist_orgids': ['o-4adkskbcff']
            }]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.maxDiff = None
        self.assertEqual(
            resources[0]['CrossAccountViolations'], [
                {'Actions': ['serverlessrepo:Deploy'],
                 'Effect': 'Allow',
                 'Principal': {'AWS': ['112233445566']},
                 'StatementId': 'b364d84f-62d2-411c-9787-3636b2b1975c'}
            ])
