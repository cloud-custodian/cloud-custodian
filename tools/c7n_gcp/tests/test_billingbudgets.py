# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest
from c7n.exceptions import PolicyValidationError
from gcp_common import BaseTest
from pytest_terraform import terraform

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


def _budget_policy(test, name, display_name, action, factory):
    return test.load_policy(
        {
            'name': name,
            'resource': 'gcp.billing-budget',
            'filters': [{'displayName': display_name}],
            'actions': [dict(type='update', **action)],
        },
        session_factory=factory,
    )


def _get_budget(policy, name):
    return policy.resource_manager.get_client().execute_query('get', {'name': name})


def _display_name(fixture, key):
    return fixture.resources['google_billing_budget'][key]['display_name']


def test_billing_budget_update_requires_a_field(test):
    with pytest.raises(PolicyValidationError):
        test.load_policy(
            {
                'name': 'billing-budget-update-empty',
                'resource': 'gcp.billing-budget',
                'actions': [{'type': 'update'}],
            }
        )


@terraform('billing_budget_update', scope='session', replay=False)
def test_billing_budget_update_last_period_amount(test, billing_budget_update):
    display_name = _display_name(billing_budget_update, 'lpa')
    factory = test.record_flight_data('bb-update-lpa')
    policy = _budget_policy(
        test, 'bb-update-lpa', display_name,
        {'use-last-period-amount': True}, factory)

    resources = policy.run()

    assert len(resources) == 1
    budget = _get_budget(policy, resources[0]['name'])
    assert 'lastPeriodAmount' in budget['amount']
    assert 'specifiedAmount' not in budget['amount']
    # Fields outside the updateMask survive the patch.
    assert budget['displayName'] == display_name
    assert [r['thresholdPercent'] for r in budget['thresholdRules']] == [0.5]


@terraform('billing_budget_update', scope='session', replay=False)
def test_billing_budget_update_add_threshold(test, billing_budget_update):
    display_name = _display_name(billing_budget_update, 'thr')
    factory = test.record_flight_data('bb-update-thr')
    policy = _budget_policy(
        test, 'bb-update-thr', display_name, {'add-threshold': 0.25}, factory)

    resources = policy.run()

    assert len(resources) == 1
    budget = _get_budget(policy, resources[0]['name'])
    rules = {r['thresholdPercent']: r.get('spendBasis') for r in budget['thresholdRules']}
    assert rules == {
        0.25: 'CURRENT_SPEND',
        0.5: 'CURRENT_SPEND',
        0.9: 'FORECASTED_SPEND',
    }
    assert 'specifiedAmount' in budget['amount']


@terraform('billing_budget_update', scope='session', replay=False)
def test_billing_budget_update_pubsub_topic(test, billing_budget_update):
    display_name = _display_name(billing_budget_update, 'topic')
    topic = billing_budget_update.resources['google_pubsub_topic']['alerts']['id']
    channel = billing_budget_update.resources['google_monitoring_notification_channel'][
        'email'
    ]['id']
    factory = test.record_flight_data('bb-update-topic')
    policy = _budget_policy(
        test, 'bb-update-topic', display_name, {'pubsub-topic': topic}, factory)

    resources = policy.run()

    assert len(resources) == 1
    rule = _get_budget(policy, resources[0]['name'])['notificationsRule']
    assert rule['pubsubTopic'] == topic
    assert rule['schemaVersion'] == '1.0'
    # Sibling fields inside the same nested message are left alone.
    assert rule['monitoringNotificationChannels'] == [channel]
    assert rule['disableDefaultIamRecipients'] is True


@terraform('billing_budget_update', scope='session', replay=False)
def test_billing_budget_update_skips_custom_period(test, billing_budget_update):
    display_name = _display_name(billing_budget_update, 'custom')
    factory = test.record_flight_data('bb-update-custom')
    policy = _budget_policy(
        test, 'bb-update-custom', display_name,
        {'use-last-period-amount': True}, factory)

    resources = policy.run()

    assert len(resources) == 1
    budget = _get_budget(policy, resources[0]['name'])
    assert 'specifiedAmount' in budget['amount']
    assert 'lastPeriodAmount' not in budget['amount']
