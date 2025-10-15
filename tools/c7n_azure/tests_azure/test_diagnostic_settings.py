# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest, arm_template
from c7n.exceptions import PolicyValidationError


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
