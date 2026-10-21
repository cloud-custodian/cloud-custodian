# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

import pytest

from ..azure_common import (
    DEFAULT_SUBSCRIPTION_ID, BaseTest, arm_template, cassette_name, strict_cassette,
)
from c7n_azure.session import Session
from c7n.exceptions import PolicyValidationError
from c7n.utils import local_session
from azure.mgmt.resource import SubscriptionClient


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


class SubscriptionTaggingTest(BaseTest):
    """Functional tests for subscription tagging actions"""

    def test_subscription_tag_and_untag(self):
        """Test tagging and untagging a subscription"""
        session = local_session(Session)
        client = SubscriptionClient(session.get_credentials())

        # Step 1: Add a tag
        p = self.load_policy({
            'name': 'test-subscription-tag',
            'resource': 'azure.subscription',
            'actions': [
                {
                    'type': 'tag',
                    'tag': 'cctest_tag',
                    'value': 'ccvalue'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the tag was added
        subscription = client.subscriptions.get(
            subscription_id=session.get_subscription_id()
        )
        subscription_dict = subscription.serialize(True)
        self.assertEqual(
            subscription_dict.get('tags', {}).get('cctest_tag'),
            'ccvalue'
        )

        # Step 2: Remove the tag
        p = self.load_policy({
            'name': 'test-subscription-untag',
            'resource': 'azure.subscription',
            'actions': [
                {
                    'type': 'untag',
                    'tags': ['cctest_tag']
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the tag was removed
        subscription = client.subscriptions.get(
            subscription_id=session.get_subscription_id()
        )
        subscription_dict = subscription.serialize(True)
        self.assertNotIn('cctest_tag', subscription_dict.get('tags', {}))

    def test_subscription_tag_trim(self):
        """Test tag-trim action on subscription

        Tag-trim removes tags to free up space while preserving specified tags.
        With space=0, it removes ALL tags except those in the preserve list.
        """
        session = local_session(Session)
        client = SubscriptionClient(session.get_credentials())

        # Step 1: Add multiple test tags
        p = self.load_policy({
            'name': 'test-subscription-add-tags-for-trim',
            'resource': 'azure.subscription',
            'actions': [
                {
                    'type': 'tag',
                    'tags': {
                        'cctest_trim1': 'value1',
                        'cctest_trim2': 'value2',
                        'cctest_trim3': 'value3',
                        'cctest_preserve': 'keep_this'
                    }
                }
            ]
        })
        p.run()

        # Verify tags were added
        subscription = client.subscriptions.get(
            subscription_id=session.get_subscription_id()
        )
        subscription_dict = subscription.serialize(True)
        tags_before = subscription_dict.get('tags', {})
        self.assertIn('cctest_trim1', tags_before)
        self.assertIn('cctest_preserve', tags_before)

        # Step 2: Trim tags with space=0, preserving only cctest_preserve
        # This should remove all tags except cctest_preserve
        p = self.load_policy({
            'name': 'test-subscription-tag-trim',
            'resource': 'azure.subscription',
            'actions': [
                {
                    'type': 'tag-trim',
                    'space': 0,
                    'preserve': ['cctest_preserve']
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Step 3: Verify tags were trimmed
        subscription = client.subscriptions.get(
            subscription_id=session.get_subscription_id()
        )
        subscription_dict = subscription.serialize(True)
        tags_after = subscription_dict.get('tags', {})

        # The preserved tag should still exist
        self.assertIn('cctest_preserve', tags_after)
        # The other test tags should be removed
        self.assertNotIn('cctest_trim1', tags_after)
        self.assertNotIn('cctest_trim2', tags_after)
        self.assertNotIn('cctest_trim3', tags_after)

    def test_subscription_mark_for_op(self):
        """Test mark-for-op action on subscription"""
        p = self.load_policy({
            'name': 'test-subscription-mark-for-op',
            'resource': 'azure.subscription',
            'actions': [
                {
                    'type': 'mark-for-op',
                    'tag': 'cctest_mark',
                    'op': 'notify',
                    'days': 7
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the tag was added with correct format
        session = local_session(Session)
        client = SubscriptionClient(session.get_credentials())
        subscription = client.subscriptions.get(subscription_id=session.get_subscription_id())
        subscription_dict = subscription.serialize(True)

        # The tag should contain the operation and date
        mark_tag = subscription_dict.get('tags', {}).get('cctest_mark')
        self.assertIsNotNone(mark_tag)
        self.assertIn('notify', mark_tag)

    def test_subscription_marked_for_op_filter(self):
        """Test marked-for-op filter on subscription

        Note: In playback mode, the cassette will have a date from when it
        was recorded. The BaseTest class patches utils.now() to return the
        date from the cassette header, ensuring the filter logic works
        consistently in both live and playback modes.
        """
        session = local_session(Session)
        client = SubscriptionClient(session.get_credentials())

        # Step 1: Mark the subscription for action (using default 4 days)
        p = self.load_policy({
            'name': 'test-subscription-mark',
            'resource': 'azure.subscription',
            'actions': [
                {
                    'type': 'mark-for-op',
                    'tag': 'cctest_filter_mark',
                    'op': 'untag'
                    # days defaults to 4 if not specified
                }
            ]
        })
        p.run()

        # Verify the mark tag was added
        subscription = client.subscriptions.get(
            subscription_id=session.get_subscription_id()
        )
        subscription_dict = subscription.serialize(True)
        mark_tag = subscription_dict.get('tags', {}).get('cctest_filter_mark')
        self.assertIsNotNone(mark_tag)
        self.assertIn('untag', mark_tag)

        # Step 2: Filter for marked subscriptions
        # Use skew=4 to match resources marked for action within 4 days
        p = self.load_policy({
            'name': 'test-subscription-marked-filter',
            'resource': 'azure.subscription',
            'filters': [
                {
                    'type': 'marked-for-op',
                    'tag': 'cctest_filter_mark',
                    'op': 'untag',
                    'skew': 4
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class SubscriptionSetActivityLogAlertTest(BaseTest):
    resource_group = 'test_subscription-activity-log-alert'
    alert_name = 'cctest-nsg-write-alert'
    conditions = [
        {'field': 'category', 'equals': 'Administrative'},
        {'field': 'operationName', 'equals': 'Microsoft.Network/networkSecurityGroups/write'},
    ]

    def _alert_policy(self, **options):
        return self.load_policy({
            'name': 'test-set-activity-log-alert',
            'resource': 'azure.subscription',
            'actions': [{
                'type': 'set-activity-log-alert',
                'name': self.alert_name,
                'resource-group': self.resource_group,
                'conditions': self.conditions,
                **options,
            }],
        }, validate=True)

    def _load_alert_policy(self, **options):
        with self.sign_out_patch():
            return self._alert_policy(**options)

    def _alert_body_for(self, **options):
        action = self._load_alert_policy(**options).resource_manager.actions[0]
        return action.alert_body({'id': f'/subscriptions/{DEFAULT_SUBSCRIPTION_ID}'})

    def _action_group_id(self):
        return (
            f'/subscriptions/{self.session.get_subscription_id()}'
            f'/resourceGroups/{self.resource_group}'
            '/providers/microsoft.insights/actionGroups/cctest-activity-alert')

    def _get_alert(self, name):
        client = self.session.client('azure.mgmt.monitor.MonitorManagementClient')
        return client.activity_log_alerts.get(self.resource_group, name)

    def test_schema_rejects_empty_name(self):
        with pytest.raises(PolicyValidationError, match="'' should be non-empty"):
            self._load_alert_policy(name='')

    def test_schema_rejects_misspelled_condition_key(self):
        with pytest.raises(PolicyValidationError, match="'equal' was unexpected"):
            self._load_alert_policy(conditions=[{'field': 'category', 'equal': 'Administrative'}])

    def test_alert_body_defaults_to_enabled_with_no_action_groups(self):
        assert self._alert_body_for() == {
            'location': 'Global',
            'properties': {
                'scopes': [f'/subscriptions/{DEFAULT_SUBSCRIPTION_ID}'],
                'condition': {'allOf': [
                    {'field': 'category', 'equals': 'Administrative'},
                    {'field': 'operationName',
                     'equals': 'Microsoft.Network/networkSecurityGroups/write'},
                ]},
                'actions': {'actionGroups': []},
                'enabled': True,
            },
        }

    def test_alert_body_sends_every_option(self):
        groups = '/subscriptions/x/resourceGroups/rg/providers/microsoft.insights/actionGroups/'

        body = self._alert_body_for(
            description='NSG writes',
            enabled=False,
            **{'action-groups': [groups + 'a', groups + 'b']})

        assert body == {
            'location': 'Global',
            'properties': {
                'scopes': [f'/subscriptions/{DEFAULT_SUBSCRIPTION_ID}'],
                'condition': {'allOf': [
                    {'field': 'category', 'equals': 'Administrative'},
                    {'field': 'operationName',
                     'equals': 'Microsoft.Network/networkSecurityGroups/write'},
                ]},
                'actions': {'actionGroups': [
                    {'actionGroupId': groups + 'a'},
                    {'actionGroupId': groups + 'b'},
                ]},
                'enabled': False,
                'description': 'NSG writes',
            },
        }

    @arm_template('subscription-activity-log-alert.json')
    @strict_cassette('set-activity-log-alert')
    def test_creates_alert_scoped_to_subscription(self):
        action_group_id = self._action_group_id()

        resources = self._alert_policy(**{'action-groups': [action_group_id]}).run()

        alert = self._get_alert(self.alert_name)
        assert len(resources) == 1
        assert alert.scopes == [f'/subscriptions/{self.session.get_subscription_id()}']
        assert [(c.field, c.equals) for c in alert.condition.all_of] == [
            ('category', 'Administrative'),
            ('operationName', 'Microsoft.Network/networkSecurityGroups/write'),
        ]
        assert [g.action_group_id.lower() for g in alert.actions.action_groups] == [
            action_group_id.lower()]
        assert alert.enabled is True

    @arm_template('subscription-activity-log-alert.json')
    @strict_cassette('replace-activity-log-alert')
    def test_rerun_replaces_existing_alert_whole(self):
        name = 'cctest-replaced-alert'
        action_group_id = self._action_group_id()
        self._alert_policy(
            name=name, description='NSG writes', **{'action-groups': [action_group_id]}).run()
        before = self._get_alert(name)

        self._alert_policy(name=name).run()

        after = self._get_alert(name)
        assert [g.action_group_id.lower() for g in before.actions.action_groups] == [
            action_group_id.lower()]
        assert before.description == 'NSG writes'
        assert after.actions.action_groups == []
        assert after.description is None
        assert after.enabled is True
