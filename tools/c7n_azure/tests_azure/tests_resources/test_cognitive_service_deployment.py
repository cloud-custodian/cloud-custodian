# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os

from ..azure_common import BaseTest, arm_template, cassette_name
from ..azure_common import requires_arm_polling
from c7n.exceptions import PolicyValidationError


@requires_arm_polling
class CognitiveServiceDeploymentTest(BaseTest):
    # Set up environment variables in test.env before running the tests
    DEFAULT_OPENAI_ACCOUNT_NAME = 'cctestcogdeploy308f6f72'
    DEFAULT_OPENAI_DEPLOYMENT_NAME = 'cctest-gpt4o-mini'

    def test_cognitive_service_deployment_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy(
                {
                    'name': 'test-azure-cognitive-service-deployment',
                    'resource': 'azure.cognitiveservice-deployment',
                },
                validate=True,
            )
            self.assertTrue(p)

    @arm_template('cognitive-service-deployment.json')
    @cassette_name('cognitiveservice-deployment-get')
    def test_cognitive_service_deployment_get_resources(self):
        deployment_name = os.environ.get(
            'AZURE_OPENAI_DEPLOYMENT_NAME',
            self.DEFAULT_OPENAI_DEPLOYMENT_NAME
        )
        p = self.load_policy(
            {
                'name': 'test-azure-cognitive-service-deployment-get',
                'resource': 'azure.cognitiveservice-deployment',
            }
        )

        resources = p.run()

        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(any(r['name'].endswith(deployment_name) for r in resources))

    @arm_template('cognitive-service-deployment.json')
    @cassette_name('cognitiveservice-deployment-filter-name')
    def test_cognitive_service_deployment_filter_by_name(self):
        deployment_name = os.environ.get(
            'AZURE_OPENAI_DEPLOYMENT_NAME',
            self.DEFAULT_OPENAI_DEPLOYMENT_NAME
        )

        p = self.load_policy(
            {
                'name': 'test-azure-cognitive-service-deployment-filter-name',
                'resource': 'azure.cognitiveservice-deployment',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name',
                        'op': 'eq',
                        'value_type': 'normalize',
                        'value': deployment_name,
                    }
                ],
            }
        )

        resources = p.run()

        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(all(r['name'] == deployment_name for r in resources))

    def test_cognitive_service_deployment_tagging_not_implemented(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    'name': 'test-tag',
                    'resource': 'azure.cognitiveservice-deployment',
                    'actions': [
                        {
                            'type': 'tag',
                            'tag': 'c7n_test_tag',
                            'value': 'true',
                        }
                    ],
                },
                validate=True,
            )

    @arm_template('cognitive-service-deployment.json')
    @cassette_name('cognitiveservice-deployment-delete')
    def test_z_cognitive_service_deployment_delete(self):
        read_policy = self.load_policy(
            {
                'name': 'test-azure-cognitive-service-deployment-read-before-delete',
                'resource': 'azure.cognitiveservice-deployment',
            }
        )

        delete_policy = self.load_policy(
            {
                'name': 'test-azure-cognitive-service-deployment-delete',
                'resource': 'azure.cognitiveservice-deployment',
                'actions': [{'type': 'delete'}],
            }
        )

        resources = read_policy.run()
        self.assertGreaterEqual(len(resources), 1)
        delete_policy.resource_manager.actions[0].process(resources)
        self.sleep_in_live_mode(10)

        remaining = read_policy.run()
        self.assertEqual(len(remaining), 0)

    @arm_template('cognitive-service-deployment.json')
    @cassette_name('cognitiveservice-deployment-get-by-id')
    def test_cognitive_service_deployment_get_resources_by_id(self):
        account_name = os.environ.get(
            'AZURE_OPENAI_ACCOUNT_NAME',
            self.DEFAULT_OPENAI_ACCOUNT_NAME
        )
        deployment_name = os.environ.get(
            'AZURE_OPENAI_DEPLOYMENT_NAME',
            self.DEFAULT_OPENAI_DEPLOYMENT_NAME
        )

        p = self.load_policy(
            {
                'name': 'test-azure-cognitive-service-deployment-get-by-id',
                'resource': 'azure.cognitiveservice-deployment',
            }
        )

        subscription_id = self.session.get_subscription_id()
        resource_id = (
            f"/subscriptions/{subscription_id}"
            "/resourceGroups/test_cognitive-service-deployment"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/deployments/{deployment_name}"
        )

        resources = p.resource_manager.get_resources([resource_id])

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], resource_id)
