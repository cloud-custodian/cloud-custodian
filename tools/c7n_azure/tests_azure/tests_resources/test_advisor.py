# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest
import pytest


@pytest.mark.skiplive
class AdvisorRecommendationTest(BaseTest):
    def test_azure_advisor_recommendation_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendations',
            'resource': 'azure.advisor-recommendation'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendation',
            'resource': 'azure.advisor-recommendation'
        })
        resources = p.run()
        self.assertTrue(len(resources) > 0)

    def test_find_by_category(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendation',
            'resource': 'azure.advisor-recommendation',
            'query': [
                {
                    'filter': "Category eq 'Cost'"
                }
            ]
        })
        resources = p.run()
        self.assertTrue(len(resources) > 0)
        for r in resources:
            if r['properties']['category'] != 'Cost':
                raise Exception('Server side filter failed')

    def test_advisor_recommendation_filter(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendation-filter',
            'resource': 'azure.subscription',
            'filters': [
                {
                    'type': 'advisor-recommendation',
                    'category': 'Cost',
                    'key': '[].properties.recommendationTypeId',
                    'op': 'contains',
                    'value': '84b1a508-fc21-49da-979e-96894f1665df',
                }
            ]
        })
        resources = p.run()
        self.assertTrue(len(resources) == 1)
        self.assertTrue(
            isinstance(resources[0]['c7n:AdvisorRecommendation'], list)
        )
        # elements should be a list
        self.assertTrue(
            isinstance(resources[0]['c7n:AdvisorRecommendation'][0], dict)
        )
