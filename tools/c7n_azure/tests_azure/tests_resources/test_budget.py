# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template


class BudgetTest(BaseTest):
    def setUp(self):
        super(BudgetTest, self).setUp()

    def test_budget_schema_validate(self):
        """Validate the budget policy schema"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-budget',
                'resource': 'azure.budget'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('budget.json')
    def test_find_budget_by_name(self):
        """Find an Azure Budget resource by name"""
        p = self.load_policy({
            'name': 'test-azure-budget',
            'resource': 'azure.budget',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cctest-budget*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
