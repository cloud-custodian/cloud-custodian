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
from mock import patch

from azure.mgmt.resource.policy.models import PolicyDefinition


class PolicyCompliance(BaseTest):

    def test_policy_compliance_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-policy-compliance',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'policy-compliant',
                     'compliant': True}
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('vm.json')
    @patch("azure.mgmt.policyinsights.operations.policy_states_operations.PolicyStatesOperations."
           "list_query_results_for_subscription")
    def test_find_by_name(self, policy_mock):
        policy_mock.return_value.value = []

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'policy-compliant',
                 'compliant': True}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'policy-compliant',
                 'compliant': False}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('emptyrg.json')
    @patch("azure.mgmt.policyinsights.operations.policy_states_operations.PolicyStatesOperations."
           "list_query_results_for_subscription")
    @patch("azure.mgmt.resource.policy.PolicyClient")
    def test_find_by_name_definition(self, client_mock, policy_mock):
        policy_mock.return_value.value = []
        client_mock.policy_definitions.list.return_value = [PolicyDefinition(display_name='TEST')]

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'policy-compliant',
                 'definitions': ['TEST'],
                 'compliant': True}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'policy-compliant',
                 'definitions': ['TEST'],
                 'compliant': False}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)
