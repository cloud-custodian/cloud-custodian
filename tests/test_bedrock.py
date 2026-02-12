# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest, event_data
from botocore.exceptions import ClientError
from pytest_terraform import terraform


class BedrockCustomModel(BaseTest):

    def test_bedrock_custom_model(self):
        session_factory = self.replay_flight_data('test_bedrock_custom_model')
        p = self.load_policy(
            {
                'name': 'bedrock-custom-model-tag',
                'resource': 'bedrock-custom-model',
                'filters': [
                    {'tag:foo': 'absent'},
                    {'tag:Owner': 'c7n'},
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    },
                    {
                        'type': 'remove-tag',
                        'tags': ['Owner']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('bedrock')
        tags = client.list_tags_for_resource(resourceARN=resources[0]['modelArn'])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, [{'key': 'foo', 'value': 'bar'}])

    def test_bedrock_custom_model_delete(self):
        session_factory = self.replay_flight_data('test_bedrock_custom_model_delete')
        p = self.load_policy(
            {
                'name': 'custom-model-delete',
                'resource': 'bedrock-custom-model',
                'filters': [{'modelName': 'c7n-test3'}],
                'actions': [{'type': 'delete'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('bedrock')
        models = client.list_custom_models().get('modelSummaries')
        self.assertEqual(len(models), 0)


class BedrockModelCustomizationJobs(BaseTest):

    def test_bedrock_customization_job_tag(self):
        session_factory = self.replay_flight_data('test_bedrock_customization_job_tag')
        base_model = "cohere.command-text-v14:7:4k"
        id = "/eys9455tunxa"
        arn = 'arn:aws:bedrock:us-east-1:644160558196:model-customization-job/' + base_model + id
        client = session_factory().client('bedrock')
        t = client.list_tags_for_resource(resourceARN=arn)['tags']
        self.assertEqual(len(t), 1)
        self.assertEqual(t, [{'key': 'Owner', 'value': 'Pratyush'}])
        p = self.load_policy(
            {
                'name': 'bedrock-model-customization-job-tag',
                'resource': 'bedrock-customization-job',
                'filters': [
                    {'tag:foo': 'absent'},
                    {'tag:Owner': 'Pratyush'},
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    },
                    {
                        'type': 'remove-tag',
                        'tags': ['Owner']
                    },
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['jobArn'], arn)
        tags = client.list_tags_for_resource(resourceARN=resources[0]['jobArn'])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, [{'key': 'foo', 'value': 'bar'}])

    def test_bedrock_customization_job_no_enc_stop(self):
        session_factory = self.replay_flight_data('test_bedrock_customization_job_no_enc_stop')
        p = self.load_policy(
            {
                'name': 'bedrock-model-customization-job-tag',
                'resource': 'bedrock-customization-job',
                'filters': [
                    {'status': 'InProgress'},
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/tes/pratyush',
                    },
                ],
                'actions': [
                    {
                        'type': 'stop'
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.push(event_data(
            "event-cloud-trail-bedrock-create-customization-jobs.json"), None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['jobName'], 'c7n-test-ab')
        client = session_factory().client('bedrock')
        status = client.get_model_customization_job(jobIdentifier=resources[0]['jobArn'])['status']
        self.assertEqual(status, 'Stopping')

    def test_bedrock_customization_jobarn_in_event(self):
        session_factory = self.replay_flight_data('test_bedrock_customization_jobarn_in_event')
        p = self.load_policy({'name': 'test-bedrock-job', 'resource': 'bedrock-customization-job'},
            session_factory=session_factory)
        resources = p.resource_manager.get_resources(["c7n-test-abcd"])
        self.assertEqual(len(resources), 1)


class BedrockAgent(BaseTest):

    def test_bedrock_agent_encryption(self):
        session_factory = self.replay_flight_data('test_bedrock_agent_encryption')
        p = self.load_policy(
            {
                'name': 'bedrock-agent',
                'resource': 'bedrock-agent',
                'filters': [
                    {'tag:c7n': 'test'},
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/tes/pratyush',
                    }
                ],
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['agentName'], 'c7n-test')

    def test_bedrock_agent_delete(self):
        session_factory = self.replay_flight_data('test_bedrock_agent_delete')
        p = self.load_policy(
            {
                "name": "bedrock-agent-delete",
                "resource": "bedrock-agent",
                "filters": [{"tag:owner": "policy"}],
                "actions": [{"type": "delete"}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        deleted_agentId = resources[0]['agentId']
        client = session_factory().client('bedrock-agent')
        with self.assertRaises(ClientError) as e:
            resources = client.get_agent(agentId=deleted_agentId)
        self.assertEqual(e.exception.response['Error']['Code'], 'ResourceNotFoundException')

    def test_bedrock_agent_base(self):
        session_factory = self.replay_flight_data('test_bedrock_agent_base')
        p = self.load_policy(
            {
                "name": "bedrock-agent-base-test",
                "resource": "bedrock-agent",
                "filters": [
                    {"tag:resource": "absent"},
                    {"tag:owner": "policy"},
                ],
                "actions": [
                   {
                        "type": "tag",
                        "tags": {"resource": "agent"}
                   },
                   {
                        "type": "remove-tag",
                        "tags": ["owner"]
                   }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('bedrock-agent')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['agentArn'])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'resource': 'agent'})


class BedrockKnowledgeBase(BaseTest):

    def test_bedrock_knowledge_base(self):
        session_factory = self.replay_flight_data('test_bedrock_knowledge_base')
        p = self.load_policy(
            {
                "name": "bedrock-knowledge-base-test",
                "resource": "bedrock-knowledge-base",
                "filters": [
                    {"tag:resource": "absent"},
                    {"tag:owner": "policy"},
                ],
                "actions": [
                   {
                        "type": "tag",
                        "tags": {"resource": "knowledge"}
                   },
                   {
                        "type": "remove-tag",
                        "tags": ["owner"]
                   }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('bedrock-agent')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['knowledgeBaseArn'])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'resource': 'knowledge'})

    def test_bedrock_knowledge_base_delete(self):
        session_factory = self.replay_flight_data('test_bedrock_knowledge_base_delete')
        p = self.load_policy(
            {
                "name": "knowledge-base-delete",
                "resource": "bedrock-knowledge-base",
                "filters": [{"tag:resource": "knowledge"}],
                "actions": [{"type": "delete"}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('bedrock-agent')
        knowledgebases = client.list_knowledge_bases().get('knowledgeBaseSummaries')
        self.assertEqual(len(knowledgebases), 0)


@terraform('bedrock_application_inference_profile')
def test_bedrock_application_inference_profile(test, bedrock_application_inference_profile):
    session_factory = test.replay_flight_data('test_bedrock_application_inference_profile')

    profile_arn = bedrock_application_inference_profile[
        'aws_bedrock_inference_profile.test_profile.arn']
    profile_name = bedrock_application_inference_profile[
        'aws_bedrock_inference_profile.test_profile.name']

    p = test.load_policy(
        {
            'name': 'bedrock-app-inference-profile-test',
            'resource': 'bedrock-inference-profile',
            # We don't filter on exact arn or name here because we want to test that only
            # *application* inference profiles are returned by default.
        }, session_factory=session_factory
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)
    test.assertIn('Tags', resources[0])
    test.assertEqual(resources[0]['inferenceProfileName'], profile_name)
    test.assertEqual(resources[0]['inferenceProfileArn'], profile_arn)

    # Verify tags are in correct format from universal_taggable
    tags = {t['Key']: t['Value'] for t in resources[0]['Tags']}
    test.assertEqual(tags['Environment'], 'test')
    test.assertEqual(tags['Owner'], 'c7n')


@terraform('bedrock_application_inference_profile_tag_actions')
def test_bedrock_application_inference_profile_tag_actions(
        test, bedrock_application_inference_profile_tag_actions):
    session_factory = test.replay_flight_data(
        'test_bedrock_application_inference_profile_tag_actions')
    client = session_factory().client('bedrock')

    profile_arn = bedrock_application_inference_profile_tag_actions[
        'aws_bedrock_inference_profile.test_profile.arn']

    # Test adding tags
    p = test.load_policy(
        {
            'name': 'bedrock-app-inference-profile-tag',
            'resource': 'bedrock-inference-profile',
            'filters': [
                {'inferenceProfileArn': profile_arn},
                {'tag:NewTag': 'absent'},
            ],
            'actions': [
                {
                    'type': 'tag',
                    'tags': {'NewTag': 'NewValue', 'AnotherTag': 'AnotherValue'}
                }
            ]
        }, session_factory=session_factory
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)

    # Verify tags were added
    tags = client.list_tags_for_resource(resourceARN=profile_arn)['tags']
    tag_dict = {t['key']: t['value'] for t in tags}
    test.assertEqual(tag_dict['NewTag'], 'NewValue')
    test.assertEqual(tag_dict['AnotherTag'], 'AnotherValue')
    test.assertEqual(tag_dict['Environment'], 'test')  # Original tag still there

    # Test removing tags
    p = test.load_policy(
        {
            'name': 'bedrock-app-inference-profile-untag',
            'resource': 'bedrock-inference-profile',
            'filters': [
                {'inferenceProfileArn': profile_arn},
            ],
            'actions': [
                {
                    'type': 'remove-tag',
                    'tags': ['AnotherTag', 'Owner']
                }
            ]
        }, session_factory=session_factory
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)

    # Verify tags were removed
    tags = client.list_tags_for_resource(resourceARN=profile_arn)['tags']
    tag_dict = {t['key']: t['value'] for t in tags}
    test.assertNotIn('AnotherTag', tag_dict)
    test.assertNotIn('Owner', tag_dict)
    test.assertEqual(tag_dict['NewTag'], 'NewValue')  # Still there
    test.assertEqual(tag_dict['Environment'], 'test')  # Still there
