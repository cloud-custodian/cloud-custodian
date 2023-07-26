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

    def test_advisor_recommendation_filter(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendation-filter',
            'resource': 'azure.disk',
            'filters': [
                {
                    'type': 'advisor-recommendation',
                    'key': '[].properties.category',
                    'value': 'Cost',
                    'value_type': 'swap',
                    'op': 'in'

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
