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
