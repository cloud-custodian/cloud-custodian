# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class SavingsPlansTests(BaseTest):

    def test_savings_plans_query(self):
        session_factory = self.replay_flight_data('test_savings_plans_query')
        p = self.load_policy({
            'name': 'savings-plans-query',
            'resource': 'aws.savings-plan'
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        # Verify the structure of a savings plan resource
        self.assertTrue('SavingsPlanId' in resources[0])
        self.assertTrue('SavingsPlanType' in resources[0])

    def test_savings_plans_filter_by_state(self):
        session_factory = self.replay_flight_data('test_savings_plans_filter_by_state')
        p = self.load_policy({
            'name': 'savings-plans-active',
            'resource': 'aws.savings-plan',
            'filters': [{
                'type': 'value',
                'key': 'State',
                'value': 'active'
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['State'], 'active')

    def test_savings_plans_filter_by_type(self):
        session_factory = self.replay_flight_data('test_savings_plans_filter_by_type')
        p = self.load_policy({
            'name': 'compute-savings-plans',
            'resource': 'aws.savings-plan',
            'filters': [{
                'type': 'value',
                'key': 'SavingsPlanType',
                'value': 'Compute'
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['SavingsPlanType'], 'Compute')
