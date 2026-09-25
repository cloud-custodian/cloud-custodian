# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class BillingBudgetTest(BaseTest):

    def test_billing_budget_query(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-query',
             'resource': 'gcp.billing-budget'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            resources[0]['name'],
            'billingAccounts/CU570D-1A4CU5-70D1A4/budgets/abc123def456')
        self.assertEqual(
            resources[1]['name'],
            'billingAccounts/CU570D-1A4CU5-70D1A4/budgets/xyz789uvw012')

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
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['name'],
            'billingAccounts/CU570D-1A4CU5-70D1A4/budgets/abc123def456')

    def test_billing_budget_filter_threshold_rules(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-high-threshold',
             'resource': 'gcp.billing-budget',
             'filters': [
                 {'type': 'value',
                  'key': 'thresholdRules[0].thresholdPercent',
                  'op': 'gte',
                  'value': 0.9}
             ]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['name'],
            'billingAccounts/CU570D-1A4CU5-70D1A4/budgets/xyz789uvw012')

    def test_billing_budget_filter_services(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-scoped-service',
             'resource': 'gcp.billing-budget',
             'filters': [
                 {'type': 'value',
                  'key': 'budgetFilter.services',
                  'op': 'contains',
                  'value': 'services/C7E2-9256-1C43'}
             ]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['name'],
            'billingAccounts/CU570D-1A4CU5-70D1A4/budgets/abc123def456')

    def test_billing_budget_filter_pubsub_topic(self):
        session_factory = self.replay_flight_data('billing-budget-query')

        policy = self.load_policy(
            {'name': 'billing-budget-has-pubsub',
             'resource': 'gcp.billing-budget',
             'filters': [
                 {'type': 'value',
                  'key': 'notificationsRule.pubsubTopic',
                  'value': 'present'}
             ]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['name'],
            'billingAccounts/CU570D-1A4CU5-70D1A4/budgets/abc123def456')

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
                "gcp:billingbudgets::cloud-custodian:budget/abc123def456",
                "gcp:billingbudgets::cloud-custodian:budget/xyz789uvw012",
            ])
