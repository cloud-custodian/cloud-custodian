# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import ANY, Mock, call, patch

from azure.core.exceptions import HttpResponseError

from .azure_common import BaseTest, arm_template, strict_cassette
from c7n.exceptions import PolicyValidationError
from c7n_azure.actions.diagnostic_settings import SetDiagnosticSettingsAction
from c7n_azure.filters import DiagnosticSettingsFilter

RESOURCE_GROUP_ID = ('/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47'
                     '/resourceGroups/test_diagnostic-settings')
WEBAPP_ID = RESOURCE_GROUP_ID + '/providers/Microsoft.Web/sites/cctestwebapp'
STORAGE_ID = RESOURCE_GROUP_ID + '/providers/Microsoft.Storage/storageAccounts/cctestdiagstorage'
WORKSPACE_ID = (RESOURCE_GROUP_ID
                + '/providers/Microsoft.OperationalInsights/workspaces/cctestworkspace')
EVENTHUB_RULE_ID = (RESOURCE_GROUP_ID + '/providers/Microsoft.EventHub/namespaces/cctesthubs'
                    '/authorizationRules/RootManageSharedAccessKey')

# A setting as the REST API returns it at 2021-05-01-preview, using the allLogs category group
ALL_LOGS_SETTING = {
    'id': WEBAPP_ID + '/providers/microsoft.insights/diagnosticSettings/ccalllogs',
    'type': 'Microsoft.Insights/diagnosticSettings',
    'name': 'ccalllogs',
    'properties': {
        'storageAccountId': STORAGE_ID,
        'workspaceId': None,
        'logs': [{
            'category': None,
            'categoryGroup': 'allLogs',
            'enabled': True,
            'retentionPolicy': {'enabled': False, 'days': 0}
        }]
    }
}


class DiagnosticSettingsFilterTest(BaseTest):

    def test_diagnostic_settings_schema_validate(self):

        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-diagnostic-settings',
                'resource': 'azure.loadbalancer',
                'filters': [
                    {
                        'type': 'diagnostic-settings',
                        'key': "logs[?category == 'LoadBalancerProbeHealthStatus'][].enabled",
                        'op': 'in',
                        'value_type': 'swap',
                        'value': True
                    }
                ]
            }, validate=False)
            self.assertTrue(p)

    @arm_template('diagnostic-settings.json')
    def test_filter_diagnostic_settings_enabled(self):
        """Verifies we can filter by a diagnostic setting
        on an azure resource.
        """

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.loadbalancer',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestdiagnostic_loadbalancer',
                    'op': 'equal'
                },
                {
                    'type': 'diagnostic-settings',
                    'key': "logs[?category == 'LoadBalancerProbeHealthStatus'][].enabled",
                    'op': 'in',
                    'value_type': 'swap',
                    'value': True
                }
            ]
        })

        resources_logs_enabled = p.run()
        self.assertEqual(len(resources_logs_enabled), 1)

        p2 = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.loadbalancer',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestdiagnostic_loadbalancer',
                    'op': 'equal'
                },
                {
                    'type': 'diagnostic-settings',
                    'key': "logs[?category == 'LoadBalancerAlertEvent'][].enabled",
                    'op': 'in',
                    'value_type': 'swap',
                    'value': True
                }
            ]
        })

        resources_logs_not_enabled = p2.run()
        self.assertEqual(len(resources_logs_not_enabled), 0)

    @arm_template('diagnostic-settings.json')
    def test_filter_diagnostic_settings_absent(self):
        """Verifies absent operation works with a diagnostic setting
        on an azure resource.
        """

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.publicip',
            'filters': [
                {
                    'type': 'value',
                    'key': "name",
                    'value': 'cctestdiagnostic_loadbalancer_public_ip'
                },
                {
                    'type': 'diagnostic-settings',
                    'key': "logs[?category == 'DDoSProtectionNotifications'][].enabled",
                    'value': 'absent'
                }
            ]
        })

        resources_logs_enabled = p.run()
        self.assertEqual(len(resources_logs_enabled), 1)

    @arm_template('diagnostic-settings.json')
    def test_filter_diagnostic_settings_present(self):
        """Verifies present operation works with a diagnostic setting
        on an azure resource.
        """

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.loadbalancer',
            'filters': [
                {
                    'type': 'diagnostic-settings',
                    'key': "logs[?category == 'LoadBalancerProbeHealthStatus'][].enabled",
                    'value': 'present'
                }
            ]
        })

        resources_logs_enabled = p.run()
        self.assertEqual(len(resources_logs_enabled), 1)

    @arm_template('vm.json')
    def test_filter_diagnostic_settings_not_enabled(self):
        """Verifies validation fails if the resource type
            does not use diagnostic settings.
        """
        policy = {
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {
                    'type': 'diagnostic-settings',
                    'key': "logs[*][].enabled",
                    'op': 'in',
                    'value_type': 'swap',
                    'value': True
                }
            ]
        }
        self.assertRaises(
            PolicyValidationError, self.load_policy, policy, validate=True)

    @arm_template('diagnostic-settings-category-group.json')
    def test_filter_diagnostic_settings_category_group(self):
        """Verifies a setting that uses the allLogs category group is visible to the filter.
        """
        p = self.load_policy({
            'name': 'test-diagnostic-settings-category-group',
            'resource': 'azure.keyvault',
            'filters': [
                {
                    'type': 'value',
                    'key': 'resourceGroup',
                    'value': 'test_diagnostic-settings-category-group'
                },
                {
                    'type': 'diagnostic-settings',
                    'key': "logs[?category_group == 'allLogs'][].enabled",
                    'op': 'in',
                    'value_type': 'swap',
                    'value': True
                }
            ]
        })

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['name'].startswith('cckvdiagcg'))

    def test_filter_diagnostic_settings_category_group_request(self):
        """Verifies the filter requests an api-version that returns category groups.

        Azure leaves such settings out below 2021-05-01-preview. Cassettes ignore
        api-version, so this asserts the request directly.
        """
        manager = Mock()
        get_by_id = manager.get_client.return_value.resources.get_by_id
        get_by_id.side_effect = [
            {'value': [ALL_LOGS_SETTING]}, {'value': []}, {'value': None}]
        f = DiagnosticSettingsFilter({
            'type': 'diagnostic-settings',
            'key': "logs[?category_group == 'allLogs'][].enabled",
            'op': 'in',
            'value_type': 'swap',
            'value': True
        }, manager=manager)
        resources = [{'id': WEBAPP_ID}, {'id': WEBAPP_ID + '-no-settings'},
                     {'id': WEBAPP_ID + '-null-value'}]

        self.assertEqual(f.process_resource_set(resources), [{'id': WEBAPP_ID}])
        manager.get_client.assert_called_once_with(
            'azure.mgmt.resource.ResourceManagementClient')
        self.assertEqual(get_by_id.call_args_list, [
            call(resource_id=r['id'] + '/providers/Microsoft.Insights/diagnosticSettings',
                 api_version='2021-05-01-preview', cls=ANY)
            for r in resources
        ])

    def test_diagnostic_settings_normalize(self):
        """Verifies raw settings take the shape of the monitor SDK's as_dict(),
        which existing policies are written against.
        """
        self.assertEqual(DiagnosticSettingsFilter._normalize(ALL_LOGS_SETTING), {
            'id': WEBAPP_ID + '/providers/microsoft.insights/diagnosticSettings/ccalllogs',
            'type': 'Microsoft.Insights/diagnosticSettings',
            'name': 'ccalllogs',
            'storage_account_id': STORAGE_ID,
            'logs': [{
                'category_group': 'allLogs',
                'enabled': True,
                'retention_policy': {'enabled': False, 'days': 0}
            }]
        })


class SetDiagnosticSettingsActionTest(BaseTest):

    def test_set_diagnostic_settings_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-set-diagnostic-settings',
                'resource': 'azure.webapp',
                'actions': [{
                    'type': 'set-diagnostic-settings',
                    'name': 'c7n-http-logs',
                    'workspaceId': WORKSPACE_ID,
                    'logs': [{'category': 'AppServiceHTTPLogs', 'enabled': True}]
                }]
            }, validate=True)
            self.assertTrue(p)

    def test_set_diagnostic_settings_validate_rejects(self):
        cases = [
            ('needs a destination',
             {'logs': [{'category': 'AppServiceHTTPLogs', 'enabled': True}]}),
            ('needs logs or metrics',
             {'workspaceId': WORKSPACE_ID}),
            ('exactly one of category or categoryGroup',
             {'workspaceId': WORKSPACE_ID,
              'logs': [{'enabled': True}]}),
            ('exactly one of category or categoryGroup',
             {'workspaceId': WORKSPACE_ID,
              'logs': [{'category': 'AppServiceHTTPLogs', 'categoryGroup': 'allLogs',
                        'enabled': True}]}),
        ]
        for message, fields in cases:
            action = {'type': 'set-diagnostic-settings', 'name': 'c7n-http-logs'}
            action.update(fields)
            with self.subTest(fields=fields), self.sign_out_patch():
                with self.assertRaisesRegex(PolicyValidationError, message):
                    self.load_policy({
                        'name': 'test-set-diagnostic-settings',
                        'resource': 'azure.webapp',
                        'actions': [action]
                    }, validate=True)

    def test_set_diagnostic_settings_name_rejects(self):
        # The name ends the request URL: empty, '/', '?' or '#' would change what gets written
        for name in (None, '', 'a/b', 'a?b', 'a#b'):
            action = {'type': 'set-diagnostic-settings', 'workspaceId': WORKSPACE_ID,
                      'logs': [{'category': 'AppServiceHTTPLogs', 'enabled': True}]}
            if name is not None:
                action['name'] = name
            with self.subTest(name=name), self.sign_out_patch():
                with self.assertRaises(PolicyValidationError):
                    self.load_policy({
                        'name': 'test-set-diagnostic-settings',
                        'resource': 'azure.webapp',
                        'actions': [action]
                    }, validate=True)

    def test_set_diagnostic_settings_not_enabled(self):
        # VMs have diagnostic_settings_enabled = False, so they get neither the filter nor this
        with self.sign_out_patch(), self.assertRaises(PolicyValidationError):
            self.load_policy({
                'name': 'test-set-diagnostic-settings',
                'resource': 'azure.vm',
                'actions': [{
                    'type': 'set-diagnostic-settings',
                    'name': 'c7n-http-logs',
                    'workspaceId': WORKSPACE_ID,
                    'metrics': [{'category': 'AllMetrics', 'enabled': True}]
                }]
            }, validate=True)

    def test_set_diagnostic_settings_request(self):
        """Verifies each resource gets a PUT to its own setting id, at an api-version
        that accepts category groups, with the policy's fields as the body.

        Cassettes ignore api-version and request bodies, so this asserts them directly.
        """
        p = self.load_policy({
            'name': 'test-set-diagnostic-settings',
            'resource': 'azure.webapp',
            'actions': [{
                'type': 'set-diagnostic-settings',
                'name': 'c7n-all-logs',
                'workspaceId': WORKSPACE_ID,
                'storageAccountId': STORAGE_ID,
                'eventHubAuthorizationRuleId': EVENTHUB_RULE_ID,
                'eventHubName': 'cctesthub',
                'logAnalyticsDestinationType': 'Dedicated',
                'logs': [{'categoryGroup': 'allLogs', 'enabled': True}],
                'metrics': [{'category': 'AllMetrics', 'enabled': True}]
            }]
        })
        action = p.resource_manager.actions[0]
        resources = [{'id': WEBAPP_ID, 'name': 'cctestwebapp'},
                     {'id': WEBAPP_ID + '-2', 'name': 'cctestwebapp-2'}]

        with patch.object(p.resource_manager, 'get_client') as get_client:
            put = get_client.return_value.resources.begin_create_or_update_by_id
            action.process(resources)

        self.assertIsInstance(action, SetDiagnosticSettingsAction)
        get_client.assert_called_with('azure.mgmt.resource.ResourceManagementClient')
        setting_ids = [r['id'] + '/providers/Microsoft.Insights/diagnosticSettings/c7n-all-logs'
                       for r in resources]
        self.assertEqual(put.call_args_list, [
            call(resource_id=setting_id, api_version='2021-05-01-preview', parameters=ANY)
            for setting_id in setting_ids
        ])
        for put_call in put.call_args_list:
            self.assertEqual(put_call.kwargs['parameters'].properties, {
                'workspaceId': WORKSPACE_ID,
                'storageAccountId': STORAGE_ID,
                'eventHubAuthorizationRuleId': EVENTHUB_RULE_ID,
                'eventHubName': 'cctesthub',
                'logAnalyticsDestinationType': 'Dedicated',
                'logs': [{'categoryGroup': 'allLogs', 'enabled': True}],
                'metrics': [{'category': 'AllMetrics', 'enabled': True}]
            })
        self.assertEqual(put.return_value.result.call_count, len(resources))

    def test_set_diagnostic_settings_raises_after_batch(self):
        """Verifies a failed write doesn't stop the rest of the batch, and still fails the run.

        The base class would swallow the error outside pytest and report success.
        """
        p = self.load_policy({
            'name': 'test-set-diagnostic-settings',
            'resource': 'azure.webapp',
            'actions': [{
                'type': 'set-diagnostic-settings',
                'name': 'c7n-http-logs',
                'workspaceId': WORKSPACE_ID,
                'logs': [{'category': 'AppServiceHTTPLogs', 'enabled': True}]
            }]
        })
        action = p.resource_manager.actions[0]
        resources = [{'id': WEBAPP_ID, 'name': 'cctestwebapp'},
                     {'id': WEBAPP_ID + '-2', 'name': 'cctestwebapp-2'}]

        with patch.object(p.resource_manager, 'get_client') as get_client:
            put = get_client.return_value.resources.begin_create_or_update_by_id
            put.side_effect = [HttpResponseError('Data sink is already used'), Mock()]
            with self.assertRaisesRegex(HttpResponseError, 'Data sink is already used'):
                action.process(resources)

        self.assertEqual([c.kwargs['resource_id'] for c in put.call_args_list], [
            r['id'] + '/providers/Microsoft.Insights/diagnosticSettings/c7n-http-logs'
            for r in resources
        ])

    @arm_template('diagnostic-settings-action.json')
    @strict_cassette('set-diagnostic-settings-http-logs')
    def test_set_diagnostic_settings_http_logs(self):
        workspace_id = (
            '/subscriptions/{}/resourceGroups/test_diagnostic-settings-action/providers'
            '/Microsoft.OperationalInsights/workspaces/cctest-diag-action-workspace'
        ).format(self.session.get_subscription_id())
        p = self.load_policy({
            'name': 'test-set-diagnostic-settings',
            'resource': 'azure.webapp',
            'filters': [
                {'type': 'value',
                 'key': 'resourceGroup',
                 'value': 'test_diagnostic-settings-action'},
                {'not': [{
                    'type': 'diagnostic-settings',
                    'key': "logs[?category == 'AppServiceHTTPLogs' && enabled]",
                    'value': 'not-null'
                }]}
            ],
            'actions': [{
                'type': 'set-diagnostic-settings',
                'name': 'cctest-http-logs',
                'workspaceId': workspace_id,
                'logs': [{'category': 'AppServiceHTTPLogs', 'enabled': True}]
            }]
        }, validate=True)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['name'].startswith('cctestdiagaction'))

        client = self.session.client('azure.mgmt.resource.ResourceManagementClient')
        setting_id = (f"{resources[0]['id']}/providers/Microsoft.Insights"
                      "/diagnosticSettings/cctest-http-logs")
        setting = client.resources.get_by_id(
            resource_id=setting_id, api_version=DiagnosticSettingsFilter.api_version).properties
        self.assertEqual(setting['workspaceId'].lower(), workspace_id.lower())
        # Azure lists every category the app supports; only the requested one is enabled
        self.assertEqual(
            [log['category'] for log in setting['logs'] if log['enabled']],
            ['AppServiceHTTPLogs'])


class EntraIDDiagnosticSettingsFilterTest(BaseTest):
    """Test diagnostic settings filter for EntraID resources."""

    def test_entraid_diagnostic_settings_schema_validate(self):
        """Test that EntraID resources support diagnostic-settings filter schema validation."""

        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-entraid-diagnostic-settings',
                'resource': 'azure.entraid-user',
                'filters': [
                    {
                        'type': 'diagnostic-settings',
                        'key': "logs[?category == 'AuditLogs'][].enabled",
                        'op': 'in',
                        'value_type': 'swap',
                        'value': True
                    }
                ]
            }, validate=False)
            self.assertTrue(p)

    def test_entraid_group_diagnostic_settings_schema_validate(self):
        """Test that EntraID group resources support diagnostic-settings filter."""

        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-entraid-group-diagnostic-settings',
                'resource': 'azure.entraid-group',
                'filters': [
                    {
                        'type': 'diagnostic-settings',
                        'key': "logs[?category == 'SignInLogs'][].enabled",
                        'value': 'present'
                    }
                ]
            }, validate=False)
            self.assertTrue(p)

    def test_entraid_organization_diagnostic_settings_schema_validate(self):
        """Test that EntraID organization resources support diagnostic-settings filter."""

        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-entraid-org-diagnostic-settings',
                'resource': 'azure.entraid-organization',
                'filters': [
                    {
                        'type': 'diagnostic-settings',
                        'key': "logs[?category == 'ProvisioningLogs'][].enabled",
                        'op': 'eq',
                        'value': False
                    }
                ]
            }, validate=False)
            self.assertTrue(p)
