# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import (
    BaseTest, arm_template, cassette_name, DEFAULT_SUBSCRIPTION_ID)
from unittest.mock import patch

from azure.core.paging import ItemPaged
from azure.mgmt.policyinsights.models import PolicyState
from azure.mgmt.resource.policy.models import PolicyDefinition

CCTESTVM_ID = (
    f'/subscriptions/{DEFAULT_SUBSCRIPTION_ID}/resourceGroups/TEST_VM'
    '/providers/Microsoft.Compute/virtualMachines/cctestvm')


def policy_states_page(*states):
    # Stand in for the SDK's return value, which is an ItemPaged: iterable, and
    # with no `.value`. A Mock would supply a `.value` the real client lacks.
    return ItemPaged(lambda token=None: None, lambda _: (None, iter(states)))


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
    @patch("azure.mgmt.policyinsights.operations.PolicyStatesOperations."
           "list_query_results_for_subscription")
    def test_find_by_name(self, policy_mock):
        policy_mock.return_value = policy_states_page()

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
    @patch("azure.mgmt.policyinsights.operations.PolicyStatesOperations."
           "list_query_results_for_subscription")
    @patch("azure.mgmt.resource.policy.PolicyClient")
    def test_find_by_name_definition(self, client_mock, policy_mock):
        policy_mock.return_value = policy_states_page()
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

    @arm_template('vm.json')
    @cassette_name('test_find_by_name')
    @patch("azure.mgmt.policyinsights.operations.PolicyStatesOperations."
           "list_query_results_for_subscription")
    def test_non_compliant_resource_is_matched(self, policy_mock):
        state = PolicyState(
            resource_id=CCTESTVM_ID,
            policy_definition_id='/providers/Microsoft.Authorization'
                                 '/policyDefinitions/test-definition')
        # A pager is consumed once, so hand each call its own, as the SDK does.
        policy_mock.side_effect = lambda **kwargs: policy_states_page(state)

        def vm_policy(compliant):
            return self.load_policy({
                'name': 'test-azure-vm',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value_type': 'normalize',
                     'value': 'cctestvm'},
                    {'type': 'policy-compliant',
                     'compliant': compliant}]
            })

        non_compliant = vm_policy(False).run()
        assert len(non_compliant) == 1
        assert non_compliant[0]['id'].lower() == CCTESTVM_ID.lower()

        assert vm_policy(True).run() == []
