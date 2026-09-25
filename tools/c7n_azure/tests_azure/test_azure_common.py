# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import Mock, patch

from .azure_common import AzureVCRBaseTest, BaseTest


class AzureCommonTest(BaseTest):

    recording_resource_group = 'test-recording-resource-group'
    parent_id = (
        '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/'
        'resourceGroups/test-rg/providers/Microsoft.MachineLearningServices/'
        'workspaces/test-workspace'
    )

    def test_recording_sanitizer_scopes_arm_resources(self):
        test_resource = {
            'id': (
                f"{self.parent_id.replace('test-rg', self.recording_resource_group)}"
                '/computes/test-cluster'
            ),
        }
        unrelated_resource = {
            'id': self.parent_id.replace(
                'test-rg',
                'private-resource-group',
            ),
        }
        response = {
            'body': {
                'data': {
                    'value': [unrelated_resource, test_resource],
                },
            },
        }

        self._scope_recorded_resource_group(response)

        self.assertEqual([test_resource], response['body']['data']['value'])

    def test_recording_sanitizer_omits_unrelated_arm_requests(self):
        unrelated_request = Mock(
            uri=(
                'https://management.azure.com/subscriptions/test/'
                'resourceGroups/private-resource-group/resources'
            ),
            body=None,
            headers={},
        )
        test_request = Mock(
            uri=(
                'https://management.azure.com/subscriptions/test/'
                f'resourceGroups/{self.recording_resource_group}/resources'
            ),
            body=None,
            headers={},
        )

        self.assertIsNone(self._request_callback(unrelated_request))
        self.assertIs(test_request, self._request_callback(test_request))

    def test_recording_sanitizer_removes_run_identity_and_git_metadata(self):
        run = {
            'runId': 'test-run',
            'createdBy': {'userName': 'Test User'},
            'lastModifiedBy': {'userPuId': 'private-id'},
            'userId': 'private-object-id',
            'properties': {
                'mlflow.source.git.repoURL': 'private-repository',
                'mlflow.source.git.branch': 'private-branch',
                'mlflow.source.git.commit': 'private-commit',
                'azureml.git.dirty': 'True',
                'ComputeTargetType': 'AmlCompute',
            },
        }
        response = {'body': {'data': {'value': [run]}}}

        AzureVCRBaseTest._response_substitutions(response)

        self.assertNotIn('createdBy', run)
        self.assertNotIn('lastModifiedBy', run)
        self.assertNotIn('userId', run)
        self.assertEqual(
            {'ComputeTargetType': 'AmlCompute'},
            run['properties'],
        )

    def test_recording_sanitizer_redacts_async_operation_signature(self):
        url = (
            'https://management.azure.com/computeOperationsStatus/operation-id'
            '?api-version=2023-04-01&service=new&t=timestamp'
            '&c=certificate&s=signature&h=hash'
        )

        sanitized = AzureVCRBaseTest._replace_async_operation_signature(url)

        self.assertIn('api-version=2023-04-01', sanitized)
        self.assertIn('service=new', sanitized)
        self.assertIn('t=timestamp', sanitized)
        self.assertIn('c=redacted', sanitized)
        self.assertIn('s=redacted', sanitized)
        self.assertIn('h=redacted', sanitized)
        self.assertNotIn('certificate', sanitized)
        self.assertNotIn('signature', sanitized)

    def test_recording_sanitizer_redacts_operation_urls_without_json_body(self):
        response = {
            'headers': {
                'azure-asyncoperation': [
                    'https://management.azure.com/providers/Microsoft.Test/'
                    'operationResults/operation-id?api-version=2023-04-01'
                    '&c=certificate&s=signature&h=hash'
                ],
                'location': [
                    'https://management.azure.com/providers/Microsoft.Test/'
                    'operationStatuses/operation-id?api-version=2023-04-01'
                    '&c=certificate&s=signature&h=hash'
                ],
            },
            'body': {'string': b''},
        }

        with patch.object(self, 'is_playback', return_value=False):
            self._response_callback(response)

        for header in ('azure-asyncoperation', 'location'):
            with self.subTest(header=header):
                value = response['headers'][header][0]
                self.assertIn('api-version=2023-04-01', value)
                self.assertIn('c=redacted', value)
                self.assertIn('s=redacted', value)
                self.assertIn('h=redacted', value)
                self.assertNotIn('certificate', value)
                self.assertNotIn('signature', value)

    def test_recording_sanitizer_redacts_every_operation_url_shape(self):
        for path in (
            'operationsStatus',
            'operationStatuses',
            'operationResults',
        ):
            with self.subTest(path=path):
                url = (
                    'https://management.azure.com/providers/Microsoft.Test/'
                    f'{path}/operation-id?api-version=2023-04-01'
                    '&c=certificate&s=signature&h=hash'
                )

                sanitized = AzureVCRBaseTest._replace_async_operation_signature(
                    url,
                )

                self.assertIn('c=redacted', sanitized)
                self.assertIn('s=redacted', sanitized)
                self.assertIn('h=redacted', sanitized)
                self.assertNotIn('certificate', sanitized)

    def test_recording_sanitizer_removes_structured_experiment_identity(self):
        experiment = {
            'experimentId': 'test-experiment',
            'name': 'cctest-current',
            'createdBy': {
                'userObjectId': 'private-object-id',
                'userTenantId': 'private-tenant-id',
                'userName': 'Test User',
                'upn': 'user@private.example',
            },
        }
        response = {'body': {'data': {'value': [experiment]}}}

        AzureVCRBaseTest._response_substitutions(response)

        self.assertNotIn('createdBy', experiment)
        self.assertEqual('test-experiment', experiment['experimentId'])

    def test_recording_sanitizer_keeps_unrelated_requests_on_playback(self):
        unrelated_request = Mock(
            uri=(
                'https://management.azure.com/subscriptions/test/'
                'resourceGroups/private-resource-group/resources'
            ),
            body=None,
            headers={},
        )

        with patch.object(self, 'is_playback', return_value=True):
            self.assertIs(
                unrelated_request,
                self._request_callback(unrelated_request),
            )
