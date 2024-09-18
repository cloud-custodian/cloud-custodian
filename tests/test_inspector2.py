# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class Inspector2FindingTest(BaseTest):
    """ Inspector V2 Tests"""
    def test_inspector2_finding(self):
        """
        Test Inspector V2 Finding resource
        default query filterCriteria will be applied to select Active findings
        """
        session_factory = self.replay_flight_data('test_inspector2_finding')
        policy = {
            'name': 'list-inspector2-findings',
            'resource': 'aws.inspector2-finding'
            }

        policy = self.load_policy(
            policy,
            session_factory=session_factory,
            config={'region': 'eu-central-1'}
        )
        resources = policy.run()
        self.assertEqual(len(resources), 6)

    def test_inspector2_finding_query_filter(self):
        """
        Test Inspector V2 Finding resource with filters
        custom filterCriteria query will be applied to select findings
        """
        session_factory = self.replay_flight_data('test_inspector2_finding_query_filter')
        policy = {
            'name': 'list-inspector2-findings-query-filter',
            'resource': 'aws.inspector2-finding',
            'query': [{'filterCriteria': {'severity': [
                {'comparison': 'EQUALS', 'value': 'MEDIUM'},
                {'comparison': 'EQUALS', 'value': 'CRITICAL'}
            ]}

            }]
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory,
            config={'region': 'eu-central-1'}
        )
        resources = policy.run()
        self.assertEqual(len(resources), 4)
