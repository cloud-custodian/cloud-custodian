# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class AdvisorRecommendationsTest(BaseTest):
    def test_azure_advisor_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendations',
            'resource': 'azure.advisor-recommendations'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendations',
            'resource': 'azure.advisor-recommendations',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccadvisorrecommendations*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
