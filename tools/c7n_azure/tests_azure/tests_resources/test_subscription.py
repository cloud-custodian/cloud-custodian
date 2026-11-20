# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import ANY, Mock, call, patch

import pytest
from azure.core.exceptions import HttpResponseError
from azure.mgmt.resource import SubscriptionClient
from c7n.exceptions import PolicyValidationError
from c7n.utils import local_session
from c7n_azure.filters import DiagnosticSettingsFilter
from c7n_azure.resources.subscription import SubscriptionDiagnosticSettingFilter
from c7n_azure.session import Session

from ..azure_common import (
    DEFAULT_SUBSCRIPTION_ID,
    BaseTest,
    arm_template,
    cassette_name,
    strict_cassette,
)


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

    def test_filter_request(self):
        """Verifies the filter requests an api-version that returns category groups, and
        keeps Azure's raw layout that policies key on (properties.logs).

        Cassettes ignore api-version, so this asserts the request directly.
        """
        setting = {'name': 'sec', 'properties': {
            'logs': [{'category': None, 'categoryGroup': 'allLogs', 'enabled': True}]}}
        session = Mock()
        get_by_id = session.client.return_value.resources.get_by_id
        get_by_id.side_effect = [{'value': [setting]}, {'value': []}, {'value': None}]
        f = SubscriptionDiagnosticSettingFilter({'type': 'diagnostic-settings'}, manager=Mock())

        self.assertEqual(f._get_subscription_diagnostic_settings(session, 'sub-1'), [setting])
        self.assertEqual(f._get_subscription_diagnostic_settings(session, 'sub-2'), [{}])
        self.assertEqual(f._get_subscription_diagnostic_settings(session, 'sub-3'), [{}])
        session.client.assert_called_with('azure.mgmt.resource.ResourceManagementClient')
        self.assertEqual(get_by_id.call_args_list, [
            call(resource_id=f'/subscriptions/{sub}/providers/Microsoft.Insights'
                             '/diagnosticSettings',
                 api_version='2021-05-01-preview', cls=ANY)
            for sub in ('sub-1', 'sub-2', 'sub-3')
        ])


SUBSCRIPTION = {'id': f'/subscriptions/{DEFAULT_SUBSCRIPTION_ID}',
                'subscriptionId': DEFAULT_SUBSCRIPTION_ID,
                'displayName': 'cctest-subscription'}
DIAG_RESOURCE_GROUP = 'test_subscription-diagnostic-settings'
DIAG_WORKSPACE_NAME = 'cctest-sub-diag-workspace'
DIAG_STORAGE_ID = (f'/subscriptions/{DEFAULT_SUBSCRIPTION_ID}/resourceGroups/'
                   f'{DIAG_RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/cctestsubdiag')
CIS_CATEGORIES = ['Administrative', 'Alert', 'Policy', 'Security']


def _workspace_id(subscription_id=DEFAULT_SUBSCRIPTION_ID):
    return (f'/subscriptions/{subscription_id}/resourceGroups/{DIAG_RESOURCE_GROUP}'
            f'/providers/Microsoft.OperationalInsights/workspaces/{DIAG_WORKSPACE_NAME}')


def _setting_id(name, subscription_id=DEFAULT_SUBSCRIPTION_ID):
    return (f'/subscriptions/{subscription_id}/providers/Microsoft.Insights'
            f'/diagnosticSettings/{name}')


def _raw_log(category, enabled):
    # The shape Azure returns at 2021-05-01-preview, nulls included
    return {'category': category, 'categoryGroup': None, 'enabled': enabled}


def _logs(categories, enabled=True):
    return [{'category': c, 'enabled': enabled} for c in categories]


class SubscriptionDiagnosticSettingsLiveMixin:
    """Reads and removes the subscription diagnostic settings a recorded test writes.

    A subscription setting outlives cleanup.sh, which only deletes the resource
    group, so each recorded test deletes the settings it creates.
    """

    def _resources_client(self):
        return self.session.client('azure.mgmt.resource.ResourceManagementClient').resources

    def _setting_id(self, name):
        return _setting_id(name, self.session.get_subscription_id())

    def _workspace_id(self):
        return _workspace_id(self.session.get_subscription_id())

    def _get_setting(self, name):
        return self._resources_client().get_by_id(
            resource_id=self._setting_id(name),
            api_version=DiagnosticSettingsFilter.api_version).properties

    def _setting_names(self):
        return [s['name'] for s in DiagnosticSettingsFilter.get_raw_settings(
            self.session.client('azure.mgmt.resource.ResourceManagementClient'),
            f'/subscriptions/{self.session.get_subscription_id()}')]

    def _delete_setting(self, name):
        self._resources_client().begin_delete_by_id(
            resource_id=self._setting_id(name),
            api_version=DiagnosticSettingsFilter.api_version).result()

    @staticmethod
    def _enabled_categories(setting):
        return sorted(log['category'] for log in setting['logs']
                      if log['enabled'] and log.get('category'))

    def _set_policy(self, name, logs):
        return self.load_policy({
            'name': 'test-sub-set-diagnostic-settings',
            'resource': 'azure.subscription',
            'actions': [{
                'type': 'set-diagnostic-settings',
                'name': name,
                'workspaceId': self._workspace_id(),
                'logs': logs,
            }],
        }, validate=True)


class SubscriptionSetDiagnosticSettingsTest(SubscriptionDiagnosticSettingsLiveMixin, BaseTest):

    def _load(self, **fields):
        action = {'type': 'set-diagnostic-settings', 'name': 'cctest-activity-log', **fields}
        with self.sign_out_patch():
            return self.load_policy({
                'name': 'test-sub-set-diagnostic-settings',
                'resource': 'azure.subscription',
                'actions': [action],
            }, validate=True)

    def test_schema_rejects_fields_subscriptions_lack(self):
        # Subscription settings have no metrics and no logAnalyticsDestinationType
        for extra in ({'metrics': [{'category': 'AllMetrics', 'enabled': True}]},
                      {'logAnalyticsDestinationType': 'Dedicated'}):
            with self.subTest(extra=extra), pytest.raises(PolicyValidationError):
                self._load(workspaceId=_workspace_id(), logs=_logs(['Administrative']),
                           **extra)

    def test_schema_requires_logs(self):
        with pytest.raises(PolicyValidationError, match="'logs' is a required property"):
            self._load(workspaceId=_workspace_id())

    @arm_template('subscription-diagnostic-settings.json')
    @strict_cassette('set-diagnostic-settings')
    def test_creates_setting_on_subscription(self):
        name = 'cctest-sub-diag-set'
        assert name not in self._setting_names()
        try:
            resources = self._set_policy(name, _logs(CIS_CATEGORIES)).run()

            setting = self._get_setting(name)
        finally:
            self._delete_setting(name)

        assert len(resources) == 1
        assert setting['workspaceId'].lower() == self._workspace_id().lower()
        assert self._enabled_categories(setting) == CIS_CATEGORIES


class SubscriptionUpdateDiagnosticSettingsTest(SubscriptionDiagnosticSettingsLiveMixin, BaseTest):

    def _load(self, logs):
        with self.sign_out_patch():
            return self.load_policy({
                'name': 'test-sub-update-diagnostic-settings',
                'resource': 'azure.subscription',
                'actions': [{'type': 'update-diagnostic-settings', 'logs': logs}],
            }, validate=True)

    def _run(self, settings, logs=None, put_side_effect=None):
        """Run the action against ``settings`` as Azure lists them, and return the PUT mock.

        Raises whatever the action raises; the mock is then on ``self.put``.
        """
        action = self._load(logs or _logs(CIS_CATEGORIES)).resource_manager.actions[0]
        with patch.object(action.manager, 'get_session') as get_session:
            resources = get_session.return_value.client.return_value.resources
            resources.get_by_id.return_value = {'value': settings}
            self.put = resources.begin_create_or_update_by_id
            self.put.side_effect = put_side_effect
            action.process([SUBSCRIPTION])
        return self.put

    def test_schema_rejects(self):
        for logs in ([],
                     [{'enabled': True}],
                     [{'category': 'Alert', 'categoryGroup': 'allLogs', 'enabled': True}],
                     [{'category': 'Alert'}]):
            with self.subTest(logs=logs), pytest.raises(PolicyValidationError):
                self._load(logs)

    def test_skips_setting_already_as_requested(self):
        # Matching ignores case, as Azure does for category names
        complete = {'name': 'complete', 'properties': {
            'storageAccountId': DIAG_STORAGE_ID,
            'logs': [_raw_log(c.lower(), True) for c in CIS_CATEGORIES],
        }}
        partial = {'name': 'partial', 'properties': {
            'storageAccountId': DIAG_STORAGE_ID,
            'logs': [_raw_log('Administrative', True)],
        }}

        put = self._run([complete, partial])

        assert [c.kwargs['resource_id'] for c in put.call_args_list] == [
            _setting_id('partial')]

    def test_disables_and_matches_category_groups(self):
        setting = {'name': 'groups', 'properties': {
            'workspaceId': _workspace_id(),
            'logs': [{'category': None, 'categoryGroup': 'allLogs', 'enabled': True},
                     _raw_log('Security', True)],
        }}

        put = self._run([setting], logs=[{'categoryGroup': 'AllLogs', 'enabled': False},
                                         {'category': 'Security', 'enabled': True}])

        assert put.call_args.kwargs['parameters'].properties['logs'] == [
            {'categoryGroup': 'allLogs', 'enabled': False},
            {'category': 'Security', 'enabled': True},
        ]

    def test_no_settings_writes_nothing(self):
        put = self._run([])

        assert put.call_count == 0

    def test_raises_after_processing_every_setting(self):
        """Verifies a failed write doesn't stop the other settings, and still fails the run."""
        settings = [{'name': name, 'properties': {
            'workspaceId': _workspace_id(), 'logs': [_raw_log('Administrative', True)]}}
            for name in ('first', 'second')]

        with pytest.raises(HttpResponseError, match='Data sink is already used'):
            self._run(settings, logs=_logs(['Alert']), put_side_effect=[
                HttpResponseError('Data sink is already used'), Mock()])

        assert [c.kwargs['resource_id'] for c in self.put.call_args_list] == [
            _setting_id('first'), _setting_id('second')]

    @arm_template('subscription-diagnostic-settings.json')
    @strict_cassette('update-diagnostic-settings')
    def test_merges_categories_into_existing_setting(self):
        name = 'cctest-sub-diag-update'
        # The action writes every setting on the subscription, so refuse to run
        # where it would touch settings this test didn't create.
        assert self._setting_names() == []
        baseline_logs = _logs(['Administrative', 'ServiceHealth']) + _logs(['Alert'], False)
        try:
            self._set_policy(name, baseline_logs).run()
            before = self._get_setting(name)

            resources = self.load_policy({
                'name': 'test-sub-update-diagnostic-settings',
                'resource': 'azure.subscription',
                'actions': [{'type': 'update-diagnostic-settings',
                             'logs': _logs(CIS_CATEGORIES)}],
            }, validate=True).run()

            after = self._get_setting(name)
        finally:
            self._delete_setting(name)

        assert len(resources) == 1
        assert self._enabled_categories(before) == ['Administrative', 'ServiceHealth']
        assert self._enabled_categories(after) == sorted(CIS_CATEGORIES + ['ServiceHealth'])
        assert after['workspaceId'].lower() == self._workspace_id().lower()


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
