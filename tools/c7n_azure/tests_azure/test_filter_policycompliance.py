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


def policy_states_pages(*pages):
    # Stand in for the SDK's return value, which is an ItemPaged: iterable, with no
    # `.value` (a Mock would supply one the real client lacks), and spread over
    # continuation pages so a filter that reads only the first page is caught.
    remaining = [list(page) for page in pages]

    def get_next(token=None):
        return remaining.pop(0) if remaining else []

    def extract_data(page):
        return ('next' if remaining else None), iter(page)

    return ItemPaged(get_next, extract_data)


def policy_state(resource_id, compliance_state='NonCompliant', definition='test-definition'):
    return PolicyState(
        resource_id=resource_id,
        compliance_state=compliance_state,
        policy_definition_id=(
            f'/providers/Microsoft.Authorization/policyDefinitions/{definition}'))


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
        policy_mock.return_value = policy_states_pages()

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
        policy_mock.return_value = policy_states_pages()
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
        # The match sits on the second page, so reading only the first fails here.
        other = policy_state('/subscriptions/x/other-vm')
        matching = policy_state(CCTESTVM_ID)
        # A pager is consumed once, so hand each call its own, as the SDK does.
        policy_mock.side_effect = lambda **kwargs: policy_states_pages([other], [matching])

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

    @arm_template('vm.json')
    @cassette_name('test_find_by_name')
    @patch("azure.mgmt.policyinsights.operations.PolicyStatesOperations."
           "list_query_results_for_subscription")
    def test_compliant_state_is_not_matched(self, policy_mock):
        # The query returns compliant records too; they must not read as findings.
        policy_mock.side_effect = lambda **kwargs: policy_states_pages(
            [policy_state(CCTESTVM_ID, compliance_state='Compliant')])

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

        assert vm_policy(False).run() == []
        assert len(vm_policy(True).run()) == 1
