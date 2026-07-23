# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform

from .common import BaseTest
from c7n.resources import boto_resource


class FakePaginator:

    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **params):
        assert params == {'maxResults': 10}
        return self.pages


class FakeClient:

    def __init__(self):
        self._pages = [
            {
                'modelDeploymentSummaries': [
                    {'modelDeploymentArn': 'arn:1', 'name': 'a'},
                    {'modelDeploymentArn': 'arn:2', 'name': 'b'},
                ]
            }
        ]

    def can_paginate(self, method_name):
        return method_name == 'list_custom_model_deployments'

    def get_paginator(self, method_name):
        assert method_name == 'list_custom_model_deployments'
        return FakePaginator(self._pages)


class FakeSession:

    def __init__(self, client):
        self._client = client

    def client(self, service_name):
        assert service_name == 'bedrock'
        return self._client


@terraform('bedrock_application_inference_profile')
def test_boto_resource_bedrock_inference_profiles(
        test, bedrock_application_inference_profile):
    session_factory = test.replay_flight_data(
        'test_bedrock_application_inference_profile', region='us-east-1')

    profile_arn = bedrock_application_inference_profile[
        'aws_bedrock_inference_profile.test_profile.arn']

    policy = test.load_policy(
        {
            'name': 'boto-resource-bedrock-inference-profile',
            'resource': 'boto-resource',
            'service': 'bedrock',
            'method': 'list_inference_profiles',
            'params': {'typeEquals': 'APPLICATION'},
            'result_key': 'inferenceProfileSummaries',
            'id-field': 'inferenceProfileArn',
            'filters': [
                {'inferenceProfileArn': profile_arn},
            ],
        },
        session_factory=session_factory,
        config={'region': 'us-east-1'},
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]['inferenceProfileArn'], profile_arn)

    selected = policy.resource_manager.get_resources([profile_arn])
    test.assertEqual(len(selected), 1)
    test.assertEqual(selected[0]['inferenceProfileArn'], profile_arn)


class TestBotoResource(BaseTest):

    def test_schema_validate(self):
        self.load_policy(
            {
                'name': 'boto-resource-schema',
                'resource': 'boto-resource',
                'service': 'bedrock',
                'method': 'list_custom_model_deployments',
            },
            validate=True,
        )

    def test_resources_and_get_resources(self):
        fake_client = FakeClient()
        self.patch(
            boto_resource,
            'local_session',
            lambda session_factory: FakeSession(fake_client),
        )

        policy = self.load_policy(
            {
                'name': 'boto-resource-bedrock',
                'resource': 'boto-resource',
                'service': 'bedrock',
                'method': 'list_custom_model_deployments',
                'params': {'maxResults': 10},
                'result_key': 'modelDeploymentSummaries',
                'id-field': 'modelDeploymentArn',
                'filters': [
                    {'name': 'b'},
                ],
            }
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['modelDeploymentArn'], 'arn:2')

        manager = policy.resource_manager
        selected = manager.get_resources(['arn:1'])
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['name'], 'a')

    def test_get_resource_manager_self_reference(self):
        policy = self.load_policy(
            {
                'name': 'boto-resource-rm',
                'resource': 'boto-resource',
                'service': 'bedrock',
                'method': 'list_custom_model_deployments',
            }
        )

        related = policy.resource_manager.get_resource_manager('boto-resource', data={
            'service': 'bedrock',
            'method': 'list_custom_model_deployments',
        })
        self.assertIsInstance(related, boto_resource.BotoResource)
