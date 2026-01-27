# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from ..azure_common import BaseTest, cassette_name


class SubscriptionTest(BaseTest):
    def setUp(self):
        super(SubscriptionTest, self).setUp()

    def test_subscription_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-add-policy',
                'resource': 'azure.subscription',
                'filters': [
                    {'type': 'missing',
                     'policy':
                         {'resource': 'azure.policyassignments',
                          'filters': [
                              {'type': 'value',
                               'key': 'properties.displayName',
                               'op': 'eq',
                               'value': 'cctestpolicy_sub'}]}}
                ],
                'actions': [
                    {'type': 'add-policy',
                     'name': 'cctestpolicy_sub',
                     'display_name': 'cctestpolicy_sub',
                     'definition_name': "Audit use of classic storage accounts"}
                ]
            }, validate=True)
            self.assertTrue(p)

    @patch('c7n_azure.resources.subscription.AddPolicy._get_definition_id')
    def test_add_policy(self, definition_patch):
        # The lookup table for policy ID's is huge
        # so just patch in the constant to reduce test impact
        definition_patch.return_value.id = \
            "/providers/Microsoft.Authorization/policyDefinitions/" \
            "404c3081-a854-4457-ae30-26a93ef643f9"

        client = self.session.client('azure.mgmt.resource.policy.PolicyClient')
        scope = '/subscriptions/{}'.format(self.session.get_subscription_id())

        self.addCleanup(client.policy_assignments.delete, scope, 'cctestpolicy_sub')

        p = self.load_policy({
            'name': 'test-add-policy',
            'resource': 'azure.subscription',
            'filters': [
                {'type': 'missing',
                 'policy':
                     {'resource': 'azure.policyassignments',
                      'filters': [
                          {'type': 'value',
                           'key': 'properties.displayName',
                           'op': 'eq',
                           'value': 'cctestpolicy_sub'}]}}
            ],
            'actions': [
                {'type': 'add-policy',
                 'name': 'cctestpolicy_sub',
                 'display_name': 'cctestpolicy_sub',
                 'definition_name': "Secure transfer to storage accounts should be enabled"}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        policy = client.policy_assignments.get(scope, 'cctestpolicy_sub')

        self.assertEqual('cctestpolicy_sub', policy.name)


class SubscriptionDiagnosticSettingsFilterTest(BaseTest):
    @cassette_name('diag')
    def test_filter_match(self):
        p = self.load_policy({
            'name': 'test-sub-diag-filter-match',
            'resource': 'azure.subscription',
            'filters': [{
                'type': 'diagnostic-settings',
                'key': "properties.logs[?category == 'Security'].enabled",
                'op': 'contains',
                'value': True
            }]
        }, validate=True)

        self.assertEqual(1, len(p.run()))

    @cassette_name('diag')
    def test_filter_no_match(self):
        p = self.load_policy({
            'name': 'test-sub-diag-filter-match',
            'resource': 'azure.subscription',
            'filters': [{
                'type': 'diagnostic-settings',
                'key': "properties.logs[?category == 'Alert'].enabled",
                'op': 'contains',
                'value': True
            }]
        }, validate=True)

        self.assertEqual(0, len(p.run()))
