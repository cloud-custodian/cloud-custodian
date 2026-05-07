# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os

from c7n.exceptions import PolicyValidationError

from ..azure_common import BaseTest, arm_template, cassette_name, requires_arm_polling


class AiFoundryDeploymentTest(BaseTest):
    def test_ai_foundry_deployment_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy(
                {
                    'name': 'test-azure-ai-foundry-deployment',
                    'resource': 'azure.ai-foundry-deployment',
                },
                validate=True,
            )
            self.assertTrue(p)

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-deployment-get')
    def test_ai_foundry_deployment_get_resources(self):
        deployment_name = os.environ.get(
            'AZURE_OPENAI_DEPLOYMENT_NAME'
        )
        p = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-deployment-get',
                'resource': 'azure.ai-foundry-deployment',
            }
        )

        resources = p.run()

        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(any(r['name'].endswith(deployment_name) for r in resources))

    def test_ai_foundry_deployment_tagging_not_implemented(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    'name': 'test-tag-ai-foundry',
                    'resource': 'azure.ai-foundry-deployment',
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

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-deployment-delete')
    def test_z_ai_foundry_deployment_delete(self):
        read_policy = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-deployment-read-before-delete',
                'resource': 'azure.ai-foundry-deployment',
            }
        )

        delete_policy = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-deployment-delete',
                'resource': 'azure.ai-foundry-deployment',
                'actions': [{'type': 'delete'}],
            }
        )

        resources = read_policy.run()
        self.assertGreaterEqual(len(resources), 1)
        delete_policy.resource_manager.actions[0].process(resources)
        self.sleep_in_live_mode(10)

        remaining = read_policy.run()
        self.assertEqual(len(remaining), 0)


class CognitiveServiceTest(BaseTest):
    def test_cognitive_service_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-cognitive-service',
                'resource': 'azure.cognitiveservice'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cognitive-service.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-cog-serv',
            'resource': 'azure.cognitiveservice',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctest-cog-serv'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class AiFoundryCognitiveServiceDeploymentTest(BaseTest):
    def test_ai_foundry_cognitiveservice_deployment_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy(
                {
                    'name': 'test-azure-ai-foundry-cognitiveservice-deployment',
                    'resource': 'azure.ai-foundry-cognitiveservice-deployment',
                },
                validate=True,
            )
            self.assertTrue(p)

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-cognitiveservice-deployment-get')
    def test_ai_foundry_cognitiveservice_deployment_get_resources(self):
        deployment_name = os.environ.get(
            'AZURE_OPENAI_DEPLOYMENT_NAME'
        )
        p = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-cognitiveservice-deployment-get',
                'resource': 'azure.ai-foundry-cognitiveservice-deployment',
            }
        )

        resources = p.run()

        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(any(r['name'].endswith(deployment_name) for r in resources))

    def test_ai_foundry_cognitiveservice_deployment_tagging_not_implemented(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    'name': 'test-tag-ai-foundry-cognitiveservice-deployment',
                    'resource': 'azure.ai-foundry-cognitiveservice-deployment',
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

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-cognitiveservice-deployment-delete')
    def test_z_ai_foundry_cognitiveservice_deployment_delete(self):
        read_policy = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-cognitiveservice-deployment-read-before-delete',
                'resource': 'azure.ai-foundry-cognitiveservice-deployment',
            }
        )

        delete_policy = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-cognitiveservice-deployment-delete',
                'resource': 'azure.ai-foundry-cognitiveservice-deployment',
                'actions': [{'type': 'delete'}],
            }
        )

        resources = read_policy.run()
        self.assertGreaterEqual(len(resources), 1)
        delete_policy.resource_manager.actions[0].process(resources)
        self.sleep_in_live_mode(10)

        remaining = read_policy.run()
        self.assertEqual(len(remaining), 0)
