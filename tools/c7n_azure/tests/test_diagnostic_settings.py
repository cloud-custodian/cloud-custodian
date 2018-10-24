# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest, arm_template
from jsonschema.exceptions import ValidationError


class DiagnosticSettingsFilterTest(BaseTest):

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
        self.assertRaises(ValidationError, self.load_policy, policy, validate=True)
