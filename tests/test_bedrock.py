# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
from .common import ACCOUNT_ID, BaseTest, event_data
from botocore.exceptions import ClientError
from pytest_terraform import terraform
from c7n.testing import C7N_FUNCTIONAL
import pytest


@terraform('bedrock_model_invocation_job')
def test_bedrock_model_invocation_job_fixture():
    pass


class BedrockModelInvocationJob(BaseTest):
    @pytest.fixture(autouse=True)
    def setup(self, bedrock_model_invocation_job):
        """Auto-use fixture to inject terraform fixture into class."""
        self.bedrock_model_invocation_job = bedrock_model_invocation_job

    @staticmethod
    def create_bedrock_invocation_job(session_factory, tf_fixture):
        """Helper to create a Bedrock model invocation job using Terraform resources."""
        # Extract outputs from the fixture's outputs attribute (fresh data from Terraform)
        role_arn = tf_fixture.outputs['role_arn']['value']
        input_s3_uri = tf_fixture.outputs['input_s3_uri']['value']
        output_s3_uri = tf_fixture.outputs['output_s3_uri']['value']
        job_name_prefix = tf_fixture.outputs['job_name_prefix']['value']

        client = session_factory().client('bedrock', region_name='us-east-1')

        # Extract unique ID from job_name_prefix (e.g., "curious-turkey")
        # This ensures each test run has a unique identifier
        unique_id = job_name_prefix.replace('c7n-batch-invocation-', '')

        response = client.create_model_invocation_job(
            jobName=job_name_prefix,
            modelId='amazon.nova-micro-v1:0',
            roleArn=role_arn,
            inputDataConfig={
                's3InputDataConfig': {
                    's3Uri': input_s3_uri
                }
            },
            outputDataConfig={
                's3OutputDataConfig': {
                    's3Uri': output_s3_uri
                }
            },
            tags=[
                {'key': 'Owner', 'value': 'c7n'},
                {'key': 'Environment', 'value': 'test'},
                {'key': 'TestRunId', 'value': unique_id}
            ]
        )

        job_arn = response['jobArn']

        return job_arn, unique_id

    def test_bedrock_model_invocation_job(self):
        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_model_invocation_job', region='us-east-1'
            )
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_model_invocation_job', region='us-east-1'
            )

        # Create the job using the helper method with Terraform resources (only in recording mode)
        # Build filters based on mode
        filters = [
            {'status': 'Submitted'},
            {'tag:Owner': 'c7n'},
            {'tag:Environment': 'test'},
        ]

        if C7N_FUNCTIONAL:
            _job_arn, unique_id = self.create_bedrock_invocation_job(
                session_factory, self.bedrock_model_invocation_job)
            # Add unique filter only in functional mode to isolate this test run
            filters.append({'tag:TestRunId': unique_id})

        p = self.load_policy(
            {
                'name': 'bedrock-model-invocation-job',
                'resource': 'bedrock-model-invocation-job',
                'filters': filters,
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'},
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('jobArn', resources[0])
        self.assertEqual(resources[0]['status'], 'Submitted')

    def test_bedrock_model_invocation_job_tag_actions(self):

        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_model_invocation_job_tag_actions_v2', region='us-east-1')
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_model_invocation_job_tag_actions_v2', region='us-east-1')

        client = session_factory().client('bedrock')

        # Build filters based on mode
        filters = [
            {'status': 'Submitted'},
            {'tag:foo': 'absent'},
            {'tag:Owner': 'c7n'},
        ]

        # Create the job using the helper method with Terraform resources (only in recording mode)
        if C7N_FUNCTIONAL:
            _job_arn, unique_id = self.create_bedrock_invocation_job(
                session_factory, self.bedrock_model_invocation_job)
            # Add unique filter only in functional mode to isolate this test run
            filters.append({'tag:TestRunId': unique_id})

        p = self.load_policy(
            {
                'name': 'bedrock-invocation-job-tag',
                'resource': 'bedrock-model-invocation-job',
                'filters': filters,
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar', 'Environment': 'test'}
                    },
                    {
                        'type': 'remove-tag',
                        'tags': ['Owner']
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify tags were added and removed
        tags = client.list_tags_for_resource(resourceARN=resources[0]['jobArn'])['tags']
        tag_dict = {t['key']: t['value'] for t in tags}
        self.assertEqual(tag_dict['foo'], 'bar')
        self.assertEqual(tag_dict['Environment'], 'test')
        self.assertNotIn('Owner', tag_dict)

    def test_bedrock_model_invocation_job_mark_for_op(self):

        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_model_invocation_job_mark_for_op_v2', region='us-east-1')
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_model_invocation_job_mark_for_op_v2', region='us-east-1')

        client = session_factory().client('bedrock')

        # Build filters based on mode
        filters = [
            {'status': 'Submitted'},
            {'tag:Owner': 'c7n'},
        ]

        unique_id = None  # Initialize for later use
        # Create the job using the helper method with Terraform resources (only in recording mode)
        if C7N_FUNCTIONAL:
            _job_arn, unique_id = self.create_bedrock_invocation_job(
                session_factory, self.bedrock_model_invocation_job)
            # Add unique filter only in functional mode to isolate this test run
            filters.append({'tag:TestRunId': unique_id})

        # Mark resources for operation
        p = self.load_policy(
            {
                'name': 'bedrock-invocation-job-mark',
                'resource': 'bedrock-model-invocation-job',
                'filters': filters,
                'actions': [
                    {
                        'type': 'mark-for-op',
                        'op': 'notify',
                        'days': 7
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        target_job_arn = resources[0]['jobArn']

        # Verify mark-for-op tag was added
        tags = client.list_tags_for_resource(resourceARN=resources[0]['jobArn'])['tags']
        tag_dict = {t['key']: t['value'] for t in tags}
        self.assertIn('maid_status', tag_dict)

        # Test marked-for-op filter - build filters based on mode
        # The skew parameter allows us to match resources that will be acted upon
        # within the next N days (in this case, 7 days since we marked them for 7 days)
        marked_filters = [
            {
                'type': 'marked-for-op',
                'op': 'notify',
                'skew': 7  # Match resources marked for action within next 7 days
            },
            {'jobArn': target_job_arn},
        ]

        if C7N_FUNCTIONAL:
            # Add unique filter only in functional mode to isolate this test run
            marked_filters.append({'tag:TestRunId': unique_id})

        p = self.load_policy(
            {
                'name': 'bedrock-invocation-job-marked',
                'resource': 'bedrock-model-invocation-job',
                'filters': marked_filters
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_bedrock_model_invocation_job_stop(self):

        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_model_invocation_job_stop', region='us-east-1')
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_model_invocation_job_stop', region='us-east-1')

        client = session_factory().client('bedrock')

        # Build filters based on mode
        filters = [
            {'status': 'Submitted'},
            {'tag:Owner': 'c7n'},
        ]

        unique_id = None  # Initialize for later use
        # Create the job using the helper method with Terraform resources (only in recording mode)
        if C7N_FUNCTIONAL:
            job_arn, unique_id = self.create_bedrock_invocation_job(
                session_factory, self.bedrock_model_invocation_job)
            # Add unique filter only in functional mode to isolate this test run
            filters.append({'tag:TestRunId': unique_id})

        # Stop the job
        p = self.load_policy(
            {
                'name': 'bedrock-invocation-job-stop',
                'resource': 'bedrock-model-invocation-job',
                'filters': filters,
                'actions': [
                    {
                        'type': 'stop'
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify job status changed to Stopping or Stopped
        job_arn = resources[0]['jobArn']
        job_status = client.get_model_invocation_job(jobIdentifier=job_arn)
        self.assertIn(job_status['status'], ['Stopping', 'Stopped'])


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
def test_bedrock_application_inference_profile_fixture():
    pass


class BedrockApplicationInferenceProfile(BaseTest):
    @pytest.fixture(autouse=True)
    def setup(self, bedrock_application_inference_profile):
        """Auto-use fixture to inject terraform fixture into class."""
        self.bedrock_application_inference_profile = bedrock_application_inference_profile

    def test_bedrock_application_inference_profile(self):
        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_application_inference_profile_v2',
                region='us-east-1')
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_application_inference_profile_v2',
                region='us-east-1')

        p = self.load_policy(
            {
                'name': 'bedrock-app-inference-profile-test',
                'resource': 'bedrock-inference-profile',
                # We don't filter on exact arn or name here because we want to test that only
                # *application* inference profiles are returned by default.
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        target_resource = resources[0]
        self.assertTrue(
            target_resource['inferenceProfileArn'].startswith(
                'arn:aws:bedrock:us-east-1:644160558196:application-inference-profile/'))
        self.assertTrue(target_resource['inferenceProfileName'].startswith('c7n-test-profile-'))

        # Verify tags are in correct format from universal_taggable
        self.assertIn('Tags', target_resource)
        tags = {t['Key']: t['Value'] for t in target_resource['Tags']}
        self.assertEqual(tags['Environment'], 'test')
        self.assertEqual(tags['Owner'], 'c7n')

    def test_bedrock_application_inference_profile_tag_actions(self):

        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_application_inference_profile_tag_actions_v2',
                region='us-east-1')
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_application_inference_profile_tag_actions_v2',
                region='us-east-1')

        client = session_factory().client('bedrock')

        profile_arn = self.bedrock_application_inference_profile[
            'aws_bedrock_inference_profile.test_profile.arn']

        # Test adding tags - use tag-based filtering that works in both modes
        add_filters = [
            {'tag:Owner': 'c7n'},
            {'tag:Environment': 'test'},
            {'tag:NewTag': 'absent'},
        ]
        if C7N_FUNCTIONAL:
            add_filters.append({'inferenceProfileArn': profile_arn})

        p = self.load_policy(
            {
                'name': 'bedrock-app-inference-profile-tag',
                'resource': 'bedrock-inference-profile',
                'filters': add_filters,
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'NewTag': 'NewValue', 'AnotherTag': 'AnotherValue'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify tags were added
        tags = client.list_tags_for_resource(
            resourceARN=resources[0]['inferenceProfileArn']
        )['tags']
        tag_dict = {t['key']: t['value'] for t in tags}
        self.assertEqual(tag_dict['NewTag'], 'NewValue')
        self.assertEqual(tag_dict['AnotherTag'], 'AnotherValue')
        self.assertEqual(tag_dict['Environment'], 'test')  # Original tag still there

        # Test removing tags
        remove_filters = [
            {'tag:Owner': 'c7n'},
            {'tag:NewTag': 'NewValue'},
        ]
        if C7N_FUNCTIONAL:
            remove_filters.append({'inferenceProfileArn': profile_arn})

        p = self.load_policy(
            {
                'name': 'bedrock-app-inference-profile-untag',
                'resource': 'bedrock-inference-profile',
                'filters': remove_filters,
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['AnotherTag', 'Owner']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify tags were removed
        tags = client.list_tags_for_resource(
            resourceARN=resources[0]['inferenceProfileArn']
        )['tags']
        tag_dict = {t['key']: t['value'] for t in tags}
        self.assertNotIn('AnotherTag', tag_dict)
        self.assertNotIn('Owner', tag_dict)
        self.assertEqual(tag_dict['NewTag'], 'NewValue')  # Still there
        self.assertEqual(tag_dict['Environment'], 'test')  # Still there

    def test_bedrock_application_inference_profile_mark_for_op(self):

        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_application_inference_profile_mark_for_op_v2',
                region='us-east-1')
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_application_inference_profile_mark_for_op_v2',
                region='us-east-1')

        client = session_factory().client('bedrock')

        profile_arn = self.bedrock_application_inference_profile[
            'aws_bedrock_inference_profile.test_profile.arn']

        # Mark resources for operation - use tag-based filtering
        mark_filters = [
            {'tag:Owner': 'c7n'},
            {'tag:Environment': 'test'},
            {'tag:maid_status': 'absent'},
        ]
        mark_filters.append({'inferenceProfileArn': profile_arn})

        p = self.load_policy(
            {
                'name': 'bedrock-inference-profile-mark',
                'resource': 'bedrock-inference-profile',
                'filters': mark_filters,
                'actions': [
                    {
                        'type': 'mark-for-op',
                        'op': 'notify',
                        'days': 7
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify mark-for-op tag was added
        tags = client.list_tags_for_resource(
            resourceARN=resources[0]['inferenceProfileArn']
        )['tags']
        tag_dict = {t['key']: t['value'] for t in tags}
        self.assertIn('maid_status', tag_dict)

        # Test marked-for-op filter
        marked_filters = [
            {
                'type': 'marked-for-op',
                'op': 'notify',
                'skew': 7
            }
        ]
        marked_filters.append({'inferenceProfileArn': profile_arn})

        p = self.load_policy(
            {
                'name': 'bedrock-inference-profile-marked',
                'resource': 'bedrock-inference-profile',
                'filters': marked_filters
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


@terraform('bedrock_inference_profile_delete')
def test_bedrock_inference_profile_delete(test, bedrock_inference_profile_delete):
    session_factory = test.replay_flight_data('test_bedrock_inference_profile_delete')
    client = session_factory().client('bedrock')

    profile_arn = bedrock_inference_profile_delete[
        'aws_bedrock_inference_profile.test_profile.arn']

    # Verify the profile exists before deletion
    profiles = client.list_inference_profiles(typeEquals='APPLICATION')['inferenceProfileSummaries']
    test.assertEqual(len(profiles), 1)
    test.assertEqual(profiles[0]['inferenceProfileArn'], profile_arn)

    # Run delete policy
    p = test.load_policy(
        {
            'name': 'bedrock-inference-profile-delete',
            'resource': 'bedrock-inference-profile',
            'filters': [
                {'inferenceProfileArn': profile_arn},
            ],
            'actions': [
                {'type': 'delete'}
            ]
        }, session_factory=session_factory
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]['inferenceProfileArn'], profile_arn)

    # Verify the profile was deleted
    profiles = client.list_inference_profiles(typeEquals='APPLICATION')['inferenceProfileSummaries']
    test.assertEqual(len(profiles), 0)


def test_bedrock_inference_profile_delete_not_found(test):
    session_factory = test.replay_flight_data('test_bedrock_inference_profile_delete_not_found')

    # Run delete policy
    p = test.load_policy(
        {
            'name': 'bedrock-inference-profile-delete',
            'resource': 'bedrock-inference-profile',
            'filters': [
                {
                    'type': 'value',
                    'key': 'inferenceProfileName',
                    'op': 'contains',
                    'value': 'c7n-delete-test'
                },
            ],
            'actions': [
                {'type': 'delete'}
            ]
        }, session_factory=session_factory
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)

    # There's nothing to test here. The error was suppressed if we've gotten to this point


def test_bedrock_inference_profile_delete_conflict(test, caplog):
    session_factory = test.replay_flight_data('test_bedrock_inference_profile_delete_conflict')

    # Run delete policy
    p = test.load_policy(
        {
            'name': 'bedrock-inference-profile-delete',
            'resource': 'bedrock-inference-profile',
            'filters': [
                {
                    'type': 'value',
                    'key': 'inferenceProfileName',
                    'op': 'contains',
                    'value': 'c7n-delete-test'
                },
            ],
            'actions': [
                {'type': 'delete'}
            ]
        }, session_factory=session_factory
    )

    with caplog.at_level(logging.WARNING):
        resources = p.run()

    test.assertEqual(len(resources), 1)

    test.assertIn(
        'Unable to delete inference profile arn:aws:bedrock:us-east-1:644160558196:application-inference-profile/1jxlkskto2ug',  # noqa
        caplog.text
    )


def test_bedrock_model_invocation_job_stop_not_found(test, caplog):
    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data(
            'test_bedrock_model_invocation_job_stop_not_found',
            region='us-east-1')
    else:
        session_factory = test.replay_flight_data(
            'test_bedrock_model_invocation_job_stop_not_found',
            region='us-east-1')

    p = test.load_policy(
        {
            'name': 'bedrock-invocation-job-stop-not-found',
            'resource': 'bedrock-model-invocation-job',
            'actions': [
                {
                    'type': 'stop'
                }
            ]
        },
        session_factory=session_factory,
        config={'region': 'us-east-1'}
    )

    account_id = ACCOUNT_ID
    if C7N_FUNCTIONAL:
        account_id = session_factory().client('sts').get_caller_identity()['Account']

    # Generate a job ARN that doesn't exist
    missing_job_arn = (
        f'arn:aws:bedrock:us-east-1:{account_id}:model-invocation-job/abc123def456'
    )

    with caplog.at_level(logging.WARNING):
        p.resource_manager.actions[0].process([{'jobArn': missing_job_arn}])

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    test.assertEqual(len(warnings), 1)
