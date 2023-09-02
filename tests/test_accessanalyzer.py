# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class AccessanalyzerFindingTest(BaseTest):
    """ IAM Access Analyzer Tests"""
    def test_access_analyzer_finding(self):
        """
        Test IAM AA Finding resource with Generic Value filter
        """
        session_factory = self.replay_flight_data('test_access_analyzer_finding')

        policy = {
            'name': 'list-access-analyzer-findings',
            'resource': 'aws.iam-access-analyzer-finding',
            'filters': [{'type': 'value',
                 'key': 'status',
                 'value': 'ACTIVE'}]
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory
        )

        resources = policy.run()
        self.assertEqual(len(resources), 2)
