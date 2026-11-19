# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from ..azure_common import BaseTest, arm_template, cassette_name

# "Kubernetes cluster containers should not share host namespaces", a
# Microsoft.Kubernetes.Data definition, which reports against components.
HOST_NAMESPACES_DEFINITION = '47a1ee2f-2a2a-4576-bf2a-e0e36709c2b8'
PRIVILEGED_CONTAINERS_DEFINITION = '95edb821-ddaf-4404-9732-666045e056b4'


def component_response(*components):
    # componentType is deliberately absent: the field exists, but its value for
    # Kubernetes has not been measured and nothing here reads it.
    return {'value': [
        {'componentId': component_id,
         'complianceState': compliance_state,
         'policyDefinitionName': definition}
        for component_id, compliance_state, definition in components]}


class AksTest(BaseTest):
    def setUp(self):
        super(AksTest, self).setUp()

    def test_aks_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-aks',
                'resource': 'azure.aks'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cdnprofile.json')
    def test_find_aks_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-aks',
            'resource': 'azure.aks',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestaks'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_policy_components_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-aks',
                'resource': 'azure.aks',
                'filters': [
                    {'type': 'policy-components',
                     'attrs': [{'complianceState': 'NonCompliant'}]}]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('aks.json')
    @cassette_name('test_find_aks_by_name')
    @patch('azure.mgmt.policyinsights.PolicyInsightsClient._send_request')
    def test_policy_components_matches_non_compliant(self, send_request):
        send_request.return_value.json.return_value = component_response(
            ('default/good-pod', 'Compliant', HOST_NAMESPACES_DEFINITION),
            ('default/bad-hostpid', 'NonCompliant', HOST_NAMESPACES_DEFINITION),
            # Non-compliant, but with a definition the policy did not name.
            ('default/privileged', 'NonCompliant', PRIVILEGED_CONTAINERS_DEFINITION))

        resources = self.load_policy({
            'name': 'test-azure-aks',
            'resource': 'azure.aks',
            'filters': [
                {'type': 'policy-components',
                 'attrs': [
                     {'complianceState': 'NonCompliant'},
                     {'policyDefinitionName': HOST_NAMESPACES_DEFINITION}]}]
        }).run()

        assert len(resources) == 1
        # Only the component that matched is annotated, not every record returned.
        assert [c['componentId'] for c in resources[0]['c7n:PolicyComponents']] == [
            'default/bad-hostpid']

        request = send_request.call_args.args[0]
        assert request.method == 'POST'
        assert request.url.startswith(resources[0]['id'])
        assert 'componentPolicyStates/latest/queryResults' in request.url
        assert 'api-version=2024-10-01' in request.url

    @arm_template('aks.json')
    @cassette_name('test_find_aks_by_name')
    @patch('azure.mgmt.policyinsights.PolicyInsightsClient._send_request')
    def test_policy_components_ignores_compliant(self, send_request):
        send_request.return_value.json.return_value = component_response(
            ('default/good-pod', 'Compliant', HOST_NAMESPACES_DEFINITION))

        resources = self.load_policy({
            'name': 'test-azure-aks',
            'resource': 'azure.aks',
            'filters': [
                {'type': 'policy-components',
                 'attrs': [{'complianceState': 'NonCompliant'}]}]
        }).run()

        assert resources == []
        # Not matching has to mean the components were read and none qualified.
        send_request.assert_called_once()
