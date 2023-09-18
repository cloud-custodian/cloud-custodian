# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class SubscriptionPolicyTest(BaseTest):
    def setUp(self):
        super(SubscriptionPolicyTest, self).setUp()

    def test_cdn_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-subscription-policy',
                'resource': 'azure.subscription-policy',
            }, validate=True)
            self.assertTrue(p)

    def test_find_profile_by_name(self):
        p = self.load_policy({
            'name': 'test-subscription-policy',
            'resource': 'azure.subscription-policy',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestsubscriptionpolicy'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
    
    @arm_template('subscription-policy.json')
    def test_subscription_policy_block(self):
        p = self.load_policy({
            'name': 'test-subscription-policy-block-false',
            'resource': 'azure.subscription-policy',
            'filters': [
                {'type': 'value',
                 'key': 'properties.blockSubscriptionsIntoTenant',
                 'value': True}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_subscription_test(self):
        p = self.load_policy({
            'name': 'test-subscription-test',
            'resource': 'azure.subscription',
            'filters': []
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
