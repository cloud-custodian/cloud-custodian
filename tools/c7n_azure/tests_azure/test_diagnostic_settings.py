# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import ANY, Mock, call

from .azure_common import BaseTest, arm_template
from c7n.exceptions import PolicyValidationError
from c7n_azure.filters import DiagnosticSettingsFilter

RESOURCE_GROUP_ID = ('/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47'
                     '/resourceGroups/test_diagnostic-settings')
WEBAPP_ID = RESOURCE_GROUP_ID + '/providers/Microsoft.Web/sites/cctestwebapp'
STORAGE_ID = RESOURCE_GROUP_ID + '/providers/Microsoft.Storage/storageAccounts/cctestdiagstorage'

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
            call(r['id'] + '/providers/Microsoft.Insights/diagnosticSettings',
                 '2021-05-01-preview', cls=ANY)
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
