# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template, cassette_name


class BudgetTest(BaseTest):

    def test_budget_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-budget',
                'resource': 'azure.budget',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'properties.amount',
                        'op': 'greater-than',
                        'value': 1000,
                    }
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('budget.json')
    @cassette_name('common')
    def test_find_by_amount(self):
        p = self.load_policy({
            'name': 'test-azure-budget',
            'resource': 'azure.budget',
            'filters': [
                {
                    'type': 'value',
                    'key': 'properties.amount',
                    'op': 'greater-than',
                    'value': 1000,
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'budget_1001')
        # Instead of actually generating cost, it's easiest to update currentSpend in the cassette
        # directly. (123.56 / 1001 ~= 12.333)
        self.assertEqual(round(resources[0]['c7n:percent-used'], 3), 12.333)
