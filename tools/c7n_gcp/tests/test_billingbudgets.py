# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest

BUDGET_1 = 'billingAccounts/0189B7-1C2253-05D127/budgets/2eb2e87a-0af1-4131-9b5e-1dacd6a41a6f'
BUDGET_2 = 'billingAccounts/0189B7-1C2253-05D127/budgets/54f10f98-316a-44b8-97b2-faf61d9748ca'


class BillingBudgetTest(BaseTest):

    def test_billing_budget_query(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-query',
             'resource': 'gcp.billing-budget'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['name'], BUDGET_1)
        self.assertEqual(resources[1]['name'], BUDGET_2)

    def test_billing_budget_filter_last_period_amount_absent(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-no-last-period-amount',
             'resource': 'gcp.billing-budget',
             'filters': [
                 {'type': 'value',
                  'key': 'amount.lastPeriodAmount',
                  'value': 'absent'}
             ]},
            session_factory=session_factory)

        resources = policy.run()
        # Both recorded budgets use specifiedAmount rather than lastPeriodAmount.
        self.assertEqual(len(resources), 2)

    def test_billing_budget_filter_threshold_rules(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-low-first-threshold',
             'resource': 'gcp.billing-budget',
             'filters': [
                 {'type': 'value',
                  'key': 'thresholdRules[0].thresholdPercent',
                  'op': 'lte',
                  'value': 0.5}
             ]},
            session_factory=session_factory)

        resources = policy.run()
        # Both budgets have 0.5 as their first alert threshold.
        self.assertEqual(len(resources), 2)

    def test_billing_budget_filter_project_level_notifications(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-project-notifications',
             'resource': 'gcp.billing-budget',
             'filters': [
                 {'type': 'value',
                  'key': 'notificationsRule.enableProjectLevelRecipients',
                  'value': True}
             ]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], BUDGET_2)

    def test_billing_budget_filter_specified_amount(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-small-amount',
             'resource': 'gcp.billing-budget',
             'filters': [
                 {'type': 'value',
                  'key': 'amount.specifiedAmount.units',
                  'op': 'eq',
                  'value': '10'}
             ]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], BUDGET_1)

    def test_billing_budget_urns(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-urns',
             'resource': 'gcp.billing-budget'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                "gcp:billingbudgets::cloud-custodian:budget/2eb2e87a-0af1-4131-9b5e-1dacd6a41a6f",
                "gcp:billingbudgets::cloud-custodian:budget/54f10f98-316a-44b8-97b2-faf61d9748ca",
            ])
