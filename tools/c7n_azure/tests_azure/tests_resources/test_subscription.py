# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import ANY, Mock, call, patch

import pytest
from azure.core.exceptions import ResourceNotFoundError
from azure.mgmt.resource import SubscriptionClient
from c7n.exceptions import PolicyValidationError
from c7n.utils import local_session
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


class SubscriptionCreateBastionHostTest(BaseTest):
    resource_group = 'test_subscription-bastion-host'
    host_name = 'cctest-bastion'
    network_name = 'cctest-bastion-vnet'
    subnet_id = (
        f'/subscriptions/{DEFAULT_SUBSCRIPTION_ID}/resourceGroups/rg'
        '/providers/Microsoft.Network/virtualNetworks/vnet/subnets/AzureBastionSubnet')
    virtual_network = {
        'name': network_name,
        'address-prefixes': ['10.0.0.0/16'],
        'subnet-prefix': '10.0.0.0/26',
    }

    def _bastion_policy(self, **options):
        return self.load_policy({
            'name': 'test-create-bastion-host',
            'resource': 'azure.subscription',
            'actions': [{
                'type': 'create-bastion-host',
                'name': self.host_name,
                'resource-group': self.resource_group,
                'location': 'southcentralus',
                **options,
            }],
        }, validate=True)

    def _load_bastion_policy(self, **options):
        with self.sign_out_patch():
            return self._bastion_policy(**options)

    def test_schema_validate(self):
        assert self._load_bastion_policy(**{'subnet-id': self.subnet_id})

    def test_validate_rejects_invalid_options(self):
        with pytest.raises(PolicyValidationError, match='exactly one of subnet-id or virtual'):
            self._load_bastion_policy(
                **{'subnet-id': self.subnet_id, 'virtual-network': self.virtual_network})
        with pytest.raises(PolicyValidationError, match="scale-units can't be set with the Basic"):
            self._load_bastion_policy(
                sku={'name': 'Basic'}, **{'scale-units': 2, 'subnet-id': self.subnet_id})

    @arm_template('subscription-bastion-host.json')
    @strict_cassette('create-bastion-host')
    def test_creates_host_and_network(self):
        client = self.session.client('azure.mgmt.network.NetworkManagementClient')
        tags = {'cctest': 'bastion'}
        with pytest.raises(ResourceNotFoundError):
            client.virtual_networks.get(self.resource_group, self.network_name)
        with pytest.raises(ResourceNotFoundError):
            client.public_ip_addresses.get(self.resource_group, f'{self.host_name}-pip')
        with pytest.raises(ResourceNotFoundError):
            client.bastion_hosts.get(self.resource_group, self.host_name)

        resources = self._bastion_policy(
            sku={'name': 'Standard'}, tags=tags,
            **{'scale-units': 3, 'virtual-network': self.virtual_network}).run()

        host = client.bastion_hosts.get(self.resource_group, self.host_name)
        network = client.virtual_networks.get(self.resource_group, self.network_name)
        public_ip = client.public_ip_addresses.get(self.resource_group, f'{self.host_name}-pip')
        assert len(resources) == 1
        assert host.sku.name == 'Standard'
        assert host.scale_units == 3
        assert host.tags == tags
        assert [c.subnet.id.lower() for c in host.ip_configurations] == [
            s.id.lower() for s in network.subnets]
        assert [c.public_ip_address.id.lower() for c in host.ip_configurations] == [
            public_ip.id.lower()]
        assert [(s.name, s.address_prefix) for s in network.subnets] == [
            ('AzureBastionSubnet', '10.0.0.0/26')]
        assert network.address_space.address_prefixes == ['10.0.0.0/16']
        assert network.tags == tags
        assert public_ip.sku.name == 'Standard'
        assert public_ip.public_ip_allocation_method == 'Static'
        assert public_ip.tags == tags

    @arm_template('subscription-bastion-host-existing-network.json')
    @strict_cassette('create-bastion-host-existing-network')
    def test_creates_host_in_existing_network(self):
        group = 'test_subscription-bastion-host-existing-network'
        client = self.session.client('azure.mgmt.network.NetworkManagementClient')
        before = client.virtual_networks.get(group, self.network_name)
        public_ip = client.public_ip_addresses.get(group, 'cctest-bastion-existing-pip')
        assert [(s.name, s.address_prefix) for s in before.subnets] == [('default', '10.0.1.0/24')]
        with pytest.raises(ResourceNotFoundError):
            client.bastion_hosts.get(group, self.host_name)

        self._bastion_policy(**{
            'resource-group': group,
            'virtual-network': self.virtual_network,
            'public-ip-address-id': public_ip.id,
        }).run()

        host = client.bastion_hosts.get(group, self.host_name)
        after = client.virtual_networks.get(group, self.network_name)
        subnets = {s.name: s for s in after.subnets}
        assert [c.subnet.id.lower() for c in host.ip_configurations] == [
            subnets['AzureBastionSubnet'].id.lower()]
        assert [c.public_ip_address.id.lower() for c in host.ip_configurations] == [
            public_ip.id.lower()]
        assert subnets['AzureBastionSubnet'].address_prefix == '10.0.0.0/26'
        assert subnets['default'].address_prefix == '10.0.1.0/24'
        assert after.address_space.address_prefixes == ['10.0.0.0/16']
        with pytest.raises(ResourceNotFoundError):
            client.public_ip_addresses.get(group, f'{self.host_name}-pip')

    @arm_template('subscription-bastion-host-existing-subnet.json')
    @strict_cassette('create-bastion-host-existing-subnet')
    def test_creates_host_in_existing_subnet(self):
        group = 'test_subscription-bastion-host-existing-subnet'
        client = self.session.client('azure.mgmt.network.NetworkManagementClient')
        subnet = client.subnets.get(group, self.network_name, 'AzureBastionSubnet')
        public_ip = client.public_ip_addresses.get(group, 'cctest-bastion-existing-pip')
        with pytest.raises(ResourceNotFoundError):
            client.bastion_hosts.get(group, self.host_name)

        self._bastion_policy(**{
            'resource-group': group,
            'subnet-id': subnet.id,
            'public-ip-address-id': public_ip.id,
        }).run()

        host = client.bastion_hosts.get(group, self.host_name)
        network = client.virtual_networks.get(group, self.network_name)
        assert [c.subnet.id.lower() for c in host.ip_configurations] == [subnet.id.lower()]
        assert [c.public_ip_address.id.lower() for c in host.ip_configurations] == [
            public_ip.id.lower()]
        assert [(s.name, s.address_prefix) for s in network.subnets] == [
            ('AzureBastionSubnet', '10.0.0.0/26')]
        with pytest.raises(ResourceNotFoundError):
            client.public_ip_addresses.get(group, f'{self.host_name}-pip')
