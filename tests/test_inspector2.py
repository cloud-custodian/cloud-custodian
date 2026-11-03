# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from c7n import query
from c7n.cache import InMemoryCache

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

    def test_inspector2_finding_cache_respects_policy_query(self):
        """
        Policies with different `query` values must not share cached findings
        """
        cache = InMemoryCache({})
        queries = []

        def list_findings(source, query):
            queries.append(query)
            return [{'findingArn': 'finding-%d' % len(queries)}]

        def load(severity):
            policy = self.load_policy(
                {
                    'name': 'inspector2-%s' % severity.lower(),
                    'resource': 'aws.inspector2-finding',
                    'query': [{'filterCriteria': {'severity': [
                        {'comparison': 'EQUALS', 'value': severity}]}}],
                },
                config={'region': 'eu-central-1'},
            )
            policy.resource_manager._cache = cache
            return policy

        with patch.object(query.DescribeSource, 'resources', list_findings):
            high = load('HIGH').resource_manager.resources()
            low = load('LOW').resource_manager.resources()
            high_again = load('HIGH').resource_manager.resources()

        self.assertEqual(len(queries), 2)
        severity = [q['filterCriteria']['severity'][0]['value'] for q in queries]
        self.assertEqual(severity, ['HIGH', 'LOW'])
        self.assertNotEqual(high, low)
        self.assertEqual(high, high_again)
