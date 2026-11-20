# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

import pytest
from azure.core.exceptions import HttpResponseError

from ..azure_common import BaseTest, arm_template, cassette_name

# "Kubernetes cluster containers should not share host namespaces", a
# Microsoft.Kubernetes.Data definition, which reports against components.
HOST_NAMESPACES_DEFINITION = '47a1ee2f-2a2a-4576-bf2a-e0e36709c2b8'
PRIVILEGED_CONTAINERS_DEFINITION = '95edb821-ddaf-4404-9732-666045e056b4'

# The cluster and the assignment the aks-policy-components template deploys.
RECORDED_CLUSTER = 'cctestakspolicy'
RECORDED_ASSIGNMENT = 'cctestakshostnamespaces'


def component_response(*components):
    return {'value': [
        {'componentId': component_id,
         'componentType': 'pod',
         'complianceState': compliance_state,
         'policyDefinitionName': definition,
         'policyAssignmentName': RECORDED_ASSIGNMENT}
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


class AksPolicyComponentsFilterTest(BaseTest):

    recording_resource_group = 'test_aks-policy-components'

    def test_policy_components_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-aks',
                'resource': 'azure.aks',
                'filters': [
                    {'type': 'policy-components',
                     'attrs': [{'complianceState': 'NonCompliant'}]}]
            }, validate=True)
            assert p

    @arm_template('aks-policy-components.json')
    def test_policy_components_matches_non_compliant(self):
        # Recorded against a cluster running a hostPID pod, with the host namespaces
        # definition assigned to its resource group. See the template's .md for the
        # setup, which cannot be done by ARM alone.
        p = self.load_policy({
            'name': 'test-azure-aks',
            'resource': 'azure.aks',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': RECORDED_CLUSTER},
                {'type': 'policy-components',
                 'attrs': [
                     {'complianceState': 'NonCompliant'},
                     {'policyDefinitionName': HOST_NAMESPACES_DEFINITION},
                     # A component is reported once per assignment naming the
                     # definition, so the fixture's own assignment is named to keep
                     # whatever else the subscription assigns out of the result.
                     {'policyAssignmentName': RECORDED_ASSIGNMENT}]}]
        })

        resources = p.run()

        assert len(resources) == 1
        assert resources[0]['name'] == RECORDED_CLUSTER
        # Only the component that matched is annotated, not every record returned.
        assert [(c['componentId'], c['componentType'])
                for c in resources[0]['c7n:PolicyComponents']] == [
            ('default/bad-hostpid', 'pod')]

    @arm_template('aks-policy-components.json')
    @cassette_name('test_policy_components_matches_non_compliant')
    @patch('azure.mgmt.policyinsights.PolicyInsightsClient._send_request')
    def test_policy_components_names_the_definition(self, send_request):
        send_request.return_value.json.return_value = component_response(
            ('default/good-pod', 'Compliant', HOST_NAMESPACES_DEFINITION),
            ('default/bad-hostpid', 'NonCompliant', HOST_NAMESPACES_DEFINITION),
            # Non-compliant, but under a definition the policy did not name.
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
        assert [c['componentId'] for c in resources[0]['c7n:PolicyComponents']] == [
            'default/bad-hostpid']

        request = send_request.call_args.args[0]
        assert request.method == 'POST'
        assert request.url.startswith(resources[0]['id'])
        assert 'componentPolicyStates/latest/queryResults' in request.url
        assert 'api-version=2024-10-01' in request.url

    @arm_template('aks-policy-components.json')
    @cassette_name('test_policy_components_matches_non_compliant')
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

    @arm_template('aks-policy-components.json')
    @cassette_name('test_policy_components_matches_non_compliant')
    @patch('azure.mgmt.policyinsights.PolicyInsightsClient._send_request')
    def test_policy_components_query_failure_raises(self, send_request):
        send_request.return_value.raise_for_status.side_effect = HttpResponseError(
            message='Forbidden')

        p = self.load_policy({
            'name': 'test-azure-aks',
            'resource': 'azure.aks',
            'filters': [
                {'type': 'policy-components',
                 'attrs': [{'complianceState': 'NonCompliant'}]}]
        })

        # Swallowing this would report the cluster as having no non-compliant
        # components, which is the wrong answer the filter exists to stop.
        with pytest.raises(HttpResponseError):
            p.run()

    @arm_template('aks-policy-components.json')
    @cassette_name('test_policy_components_matches_non_compliant')
    @patch('azure.mgmt.policyinsights.PolicyInsightsClient._send_request')
    def test_policy_components_count(self, send_request):
        send_request.return_value.json.return_value = component_response(
            ('default/bad-one', 'NonCompliant', HOST_NAMESPACES_DEFINITION),
            ('default/bad-two', 'NonCompliant', HOST_NAMESPACES_DEFINITION))

        resources = self.load_policy({
            'name': 'test-azure-aks',
            'resource': 'azure.aks',
            'filters': [
                {'type': 'policy-components',
                 'attrs': [{'complianceState': 'NonCompliant'}],
                 'count': 1,
                 'count_op': 'gt'}]
        }).run()

        assert len(resources) == 1
