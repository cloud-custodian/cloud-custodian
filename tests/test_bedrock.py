# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
from unittest import mock

import pytest

from .common import ACCOUNT_ID, BaseTest, event_data
from botocore.exceptions import ClientError
from pytest_terraform import terraform
from c7n.exceptions import PolicyValidationError
from c7n.resources.bedrock import (
    get_bedrock_output_artifact_prefix, get_bedrock_output_lifecycle,
    parse_bedrock_output_s3_uri)
from c7n.testing import C7N_FUNCTIONAL


class BedrockModelInvocationJob(BaseTest):
    @staticmethod
    def create_bedrock_invocation_job(session_factory, tf_fixture):
        """Helper to create a Bedrock model invocation job using Terraform resources."""
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


class BedrockFoundationModel(BaseTest):

    def test_bedrock_foundation_model_query(self):
        session_factory = self.replay_flight_data('test_bedrock_foundation_model_query')
        p = self.load_policy(
            {
                'name': 'bedrock-foundation-model-query',
                'resource': 'bedrock-foundation-model',
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        # Verify expected fields are present
        model = resources[0]
        self.assertIn('modelId', model)
        self.assertIn('modelArn', model)
        self.assertIn('modelName', model)
        self.assertIn('providerName', model)
        self.assertIn('inputModalities', model)
        self.assertIn('outputModalities', model)
        self.assertIn('inferenceTypesSupported', model)
        self.assertIn('modelLifecycle', model)

    def test_bedrock_foundation_model_filter_by_provider(self):
        session_factory = self.replay_flight_data(
            'test_bedrock_foundation_model_filter_by_provider')
        p = self.load_policy(
            {
                'name': 'bedrock-foundation-model-by-provider',
                'resource': 'bedrock-foundation-model',
                'query': [
                    {'byProvider': 'Amazon'},
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        for model in resources:
            self.assertEqual(model['providerName'], 'Amazon')

    def test_bedrock_foundation_model_filter_by_customization_type(self):
        session_factory = self.replay_flight_data(
            'test_bedrock_foundation_model_filter_by_customization_type')
        p = self.load_policy(
            {
                'name': 'bedrock-foundation-model-by-customization',
                'resource': 'bedrock-foundation-model',
                'query': [
                    {'byCustomizationType': 'FINE_TUNING'},
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        for model in resources:
            self.assertIn('FINE_TUNING', model['customizationsSupported'])

    def test_bedrock_foundation_model_filter_by_output_modality(self):
        session_factory = self.replay_flight_data(
            'test_bedrock_foundation_model_filter_by_output_modality')
        p = self.load_policy(
            {
                'name': 'bedrock-foundation-model-by-output-modality',
                'resource': 'bedrock-foundation-model',
                'query': [
                    {'byOutputModality': 'TEXT'},
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        for model in resources:
            self.assertIn('TEXT', model['outputModalities'])

    def test_bedrock_foundation_model_filter_by_inference_type(self):
        session_factory = self.replay_flight_data(
            'test_bedrock_foundation_model_filter_by_inference_type')
        p = self.load_policy(
            {
                'name': 'bedrock-foundation-model-by-inference-type',
                'resource': 'bedrock-foundation-model',
                'query': [
                    {'byInferenceType': 'ON_DEMAND'},
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        for model in resources:
            self.assertIn('ON_DEMAND', model['inferenceTypesSupported'])

    def test_bedrock_foundation_model_value_filter(self):
        session_factory = self.replay_flight_data(
            'test_bedrock_foundation_model_value_filter')
        p = self.load_policy(
            {
                'name': 'bedrock-foundation-model-value-filter',
                'resource': 'bedrock-foundation-model',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'modelLifecycle.status',
                        'value': 'ACTIVE',
                    },
                    {
                        'type': 'value',
                        'key': 'outputModalities',
                        'value': 'TEXT',
                        'op': 'contains',
                    },
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        for model in resources:
            self.assertEqual(model['modelLifecycle']['status'], 'ACTIVE')
            self.assertIn('TEXT', model['outputModalities'])


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

    def test_bedrock_agent_metrics(self):
        session_factory = self.replay_flight_data('test_bedrock_agent_metrics', region='us-east-2')
        p = self.load_policy(
            {"name": "bedrock-agent-metrics",
             "resource": "bedrock-agent",
             "filters": [
                 {"type": "metrics",
                 "name": "InvocationCount",
                 "statistics": "Sum",
                 "days": 30,
                 "value": 0,
                 "op": "gt",
                 "missing-value": 0}
             ]}, config={"region": "us-east-2"},
            session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

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


class BedrockApplicationInferenceProfile(BaseTest):
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

        # Test adding tags - use tag-based filtering that works in both modes
        add_filters = [
            {'tag:Owner': 'c7n'},
            {'tag:Environment': 'test'},
            {'tag:NewTag': 'absent'},
        ]
        if C7N_FUNCTIONAL:
            profile_arn = self.bedrock_application_inference_profile[
                'aws_bedrock_inference_profile.test_profile.arn']
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
            profile_arn = self.bedrock_application_inference_profile[
                'aws_bedrock_inference_profile.test_profile.arn']
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

        # Mark resources for operation - use tag-based filtering
        mark_filters = [
            {'tag:Owner': 'c7n'},
            {'tag:Environment': 'test'},
            {'tag:maid_status': 'absent'},
        ]
        if C7N_FUNCTIONAL:
            profile_arn = self.bedrock_application_inference_profile[
                'aws_bedrock_inference_profile.test_profile.arn']
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
        if C7N_FUNCTIONAL:
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


class TestBedrockEvaluationOutputRetention(BaseTest):

    def get_filter(self, data=None, session_factory=None):
        filter_data = {
            'type': 'output-retention',
            'key': '"c7n:BedrockEvaluationOutput".EffectiveExpirationDays',
            'op': 'eq',
            'value': 30,
        }
        filter_data.update(data or {})
        policy = self.load_policy(
            {
                'name': 'bedrock-evaluation-output-retention',
                'resource': 'bedrock-evaluation-job',
                'filters': [filter_data],
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'},
        )
        return policy.resource_manager.filters[0]

    def test_parse_uri(self):
        cases = (
            ('s3://example/evaluations/', ('example', 'evaluations/', None)),
            ('s3://example/a%20b/', ('example', 'a%20b/', None)),
            (None, (None, None, 'missing-uri')),
            ('', (None, None, 'missing-uri')),
            ('https://example/key', (None, None, 'invalid-uri')),
            ('s3:///key', (None, None, 'invalid-uri')),
            ('s3://example/key?version=1', (None, None, 'invalid-uri')),
        )
        for uri, expected in cases:
            assert parse_bedrock_output_s3_uri(uri) == expected

    def test_lifecycle_calculation(self):
        rules = [
            {'ID': 'root-no-filter', 'Status': 'Enabled', 'Expiration': {'Days': 90}},
            {'ID': 'root-empty-filter', 'Status': 'Enabled', 'Filter': {},
             'Expiration': {'Days': 80}},
            {'ID': 'root-empty-prefix', 'Status': 'Enabled', 'Filter': {'Prefix': ''},
             'Expiration': {'Days': 70}},
            {'ID': 'legacy', 'Status': 'Enabled', 'Prefix': 'evaluations/',
             'Expiration': {'Days': 60}},
            {'ID': 'direct', 'Status': 'Enabled', 'Filter': {'Prefix': 'evaluations/a'},
             'Expiration': {'Days': 30}},
            {'ID': 'and', 'Status': 'Enabled',
             'Filter': {'And': {'Prefix': 'evaluations/a/b'}},
             'Expiration': {'Days': 20}},
            {'ID': 'not-covering', 'Status': 'Enabled', 'Filter': {'Prefix': 'other/'},
             'Expiration': {'Days': 1}},
            {'ID': 'disabled', 'Status': 'Disabled', 'Filter': {'Prefix': 'evaluations/'},
             'Expiration': {'Days': 2}},
            {'ID': 'tagged', 'Status': 'Enabled',
             'Filter': {'Prefix': 'evaluations/', 'Tag': {'Key': 'a', 'Value': 'b'}},
             'Expiration': {'Days': 3}},
            {'ID': 'and-size', 'Status': 'Enabled',
             'Filter': {'And': {'Prefix': 'evaluations/', 'ObjectSizeGreaterThan': 1}},
             'Expiration': {'Days': 4}},
            {'ID': 'date-only', 'Status': 'Enabled', 'Filter': {'Prefix': 'evaluations/'},
             'Expiration': {'Date': '2030-01-01'}},
        ]
        matched, effective = get_bedrock_output_lifecycle(
            {'Rules': rules}, 'evaluations/a/b/results')
        assert [r['ID'] for r in matched] == [
            'root-no-filter', 'root-empty-filter', 'root-empty-prefix', 'legacy',
            'direct', 'and', 'disabled', 'tagged', 'and-size', 'date-only']
        assert effective == 20
        assert get_bedrock_output_lifecycle(None, 'evaluations/') == ([], None)

    def test_versioned_lifecycle_calculation(self):
        lifecycle = {'Rules': [
            {'ID': 'current', 'Status': 'Enabled',
             'Filter': {'Prefix': 'evaluations/'},
             'Expiration': {'Days': 30}},
            {'ID': 'noncurrent', 'Status': 'Enabled',
             'Filter': {'Prefix': 'evaluations/'},
             'NoncurrentVersionExpiration': {'NoncurrentDays': 10}},
        ]}
        matched, effective = get_bedrock_output_lifecycle(
            lifecycle, 'evaluations/job/id/', {'Status': 'Enabled'})
        assert [r['ID'] for r in matched] == ['current', 'noncurrent']
        assert effective == 40

        matched, effective = get_bedrock_output_lifecycle(
            {'Rules': [lifecycle['Rules'][0]]},
            'evaluations/job/id/',
            {'Status': 'Enabled'})
        assert [r['ID'] for r in matched] == ['current']
        assert effective is None

        matched, effective = get_bedrock_output_lifecycle(
            lifecycle, 'evaluations/job/id/', {'Status': 'Suspended'})
        assert [r['ID'] for r in matched] == ['current', 'noncurrent']
        assert effective == 40

        matched, effective = get_bedrock_output_lifecycle(
            {'Rules': [
                lifecycle['Rules'][0],
                {'ID': 'newer-noncurrent', 'Status': 'Enabled',
                 'Filter': {'Prefix': 'evaluations/'},
                 'NoncurrentVersionExpiration': {
                     'NoncurrentDays': 10, 'NewerNoncurrentVersions': 2}},
            ]}, 'evaluations/job/id/', {'Status': 'Enabled'})
        assert [r['ID'] for r in matched] == ['current', 'newer-noncurrent']
        assert effective is None

    def test_artifact_prefix_lifecycle_calculation(self):
        resource = {
            'jobName': 'my-job',
            'jobArn': 'arn:aws:bedrock:us-east-1:123456789012:evaluation-job/abc123',
        }
        for configured_prefix in ('evaluations', 'evaluations/'):
            artifact_prefix = get_bedrock_output_artifact_prefix(
                configured_prefix, resource)
            assert artifact_prefix == 'evaluations/my-job/abc123/'
            matched, effective = get_bedrock_output_lifecycle(
                {'Rules': [
                    {'ID': 'parent', 'Status': 'Enabled',
                     'Filter': {'Prefix': 'evaluations/'},
                     'Expiration': {'Days': 90}},
                    {'ID': 'job', 'Status': 'Enabled',
                     'Filter': {'Prefix': 'evaluations/my-job/'},
                     'Expiration': {'Days': 30}},
                    {'ID': 'job-id', 'Status': 'Enabled',
                     'Filter': {'Prefix': 'evaluations/my-job/abc123/'},
                     'Expiration': {'Days': 20}},
                ]}, artifact_prefix)
            assert [r['ID'] for r in matched] == ['parent', 'job', 'job-id']
            assert effective == 20

    def test_value_comparisons(self):
        for op, value, expected in (
                ('gt', 20, True), ('lt', 40, True),
                ('eq', 30, True), ('gt', 30, False)):
            output_filter = self.get_filter({'op': op, 'value': value})
            output_filter._augment_buckets = mock.Mock(return_value={
                'bucket': {
                    'Name': 'bucket',
                    'Location': {'LocationConstraint': None},
                    'Tags': [],
                    'Lifecycle': {'Rules': [{
                        'ID': 'thirty-days', 'Status': 'Enabled',
                        'Filter': {'Prefix': 'evaluations/job/id/'},
                        'Expiration': {'Days': 30},
                    }]},
                }})
            job = {
                'jobName': 'job', 'jobArn': 'arn:aws:bedrock:r:a:evaluation-job/id',
                'outputDataConfig': {'s3Uri': 's3://bucket/evaluations'}}
            resources = output_filter.process([job])
            assert bool(resources) is expected
            assert ('c7n:OutputBucket' in job) is expected

    def test_absent_value_error_context(self):
        cases = (
            (None, {}, 'missing-uri'),
            ('not-an-s3-uri', {}, 'invalid-uri'),
            ('s3://missing/evaluations/', {
                'missing': {
                    'Name': 'missing', 'Location': {}, 'Tags': [],
                    'c7n:BedrockOutputBucketError': 'bucket-not-found'}},
             'bucket-not-found'),
            ('s3://denied/evaluations/', {
                'denied': {
                    'Name': 'denied', 'Location': {'LocationConstraint': None}, 'Tags': [],
                    'c7n:DeniedMethods': ['get_bucket_lifecycle_configuration']}},
             'lifecycle-access-denied'),
        )
        for uri, buckets, error in cases:
            output_filter = self.get_filter({'value': 'absent', 'op': 'eq'})
            output_filter._augment_buckets = mock.Mock(return_value=buckets)
            job = {'outputDataConfig': {}}
            if uri is not None:
                job['outputDataConfig']['s3Uri'] = uri
            assert output_filter.process([job]) == [job]
            output = job['c7n:OutputBucket']['c7n:BedrockEvaluationOutput']
            assert output['Error'] == error
            assert 'EffectiveExpirationDays' not in output

    def test_shared_bucket_augmented_once_and_context_isolated(self):
        output_filter = self.get_filter({'op': 'gt', 'value': 0})
        bucket = {
            'Name': 'bucket', 'Location': {'LocationConstraint': None}, 'Tags': [],
            'Lifecycle': {'Rules': [
                {'ID': 'a', 'Status': 'Enabled', 'Filter': {'Prefix': 'a/'},
                 'Expiration': {'Days': 10}},
                {'ID': 'b', 'Status': 'Enabled', 'Filter': {'Prefix': 'b/'},
                 'Expiration': {'Days': 20}},
            ]}}
        output_filter._augment_buckets = mock.Mock(return_value={'bucket': bucket})
        jobs = [
            {'jobName': 'a', 'jobArn': 'arn:aws:bedrock:r:a:evaluation-job/id-a',
             'outputDataConfig': {'s3Uri': 's3://bucket/a/results'}},
            {'jobName': 'b', 'jobArn': 'arn:aws:bedrock:r:a:evaluation-job/id-b',
             'outputDataConfig': {'s3Uri': 's3://bucket/b/results'}},
        ]
        assert output_filter.process(jobs) == jobs
        output_filter._augment_buckets.assert_called_once_with(['bucket'])
        first = jobs[0]['c7n:OutputBucket']['c7n:BedrockEvaluationOutput']
        second = jobs[1]['c7n:OutputBucket']['c7n:BedrockEvaluationOutput']
        assert ([r['ID'] for r in first['PrefixMatchedLifecycleRules']],
                first['EffectiveExpirationDays']) == (['a'], 10)
        assert ([r['ID'] for r in second['PrefixMatchedLifecycleRules']],
                second['EffectiveExpirationDays']) == (['b'], 20)
        assert jobs[0]['c7n:OutputBucket'] is not jobs[1]['c7n:OutputBucket']
        assert 'c7n:BedrockEvaluationOutput' not in bucket

    def test_retention_augmentation_and_no_list_buckets(self):
        client = mock.MagicMock()
        client.meta.region_name = 'us-east-1'
        client.get_bucket_location.return_value = {'LocationConstraint': None}
        client.get_bucket_tagging.return_value = {'TagSet': []}
        client.get_bucket_versioning.return_value = {'Status': 'Enabled'}
        client.get_bucket_lifecycle_configuration.return_value = {'Rules': [{
            'ID': 'retention', 'Status': 'Enabled',
            'Filter': {'Prefix': 'a/a/id-a/'},
            'Expiration': {'Days': 30},
            'NoncurrentVersionExpiration': {'NoncurrentDays': 10},
        }]}
        session = mock.MagicMock()
        session.client.return_value = client

        def session_factory():
            return session

        output_filter = self.get_filter({'op': 'eq', 'value': 40}, session_factory)
        jobs = [
            {'jobName': 'a', 'jobArn': 'arn:aws:bedrock:r:a:evaluation-job/id-a',
             'outputDataConfig': {'s3Uri': 's3://bucket/a'}},
            {'jobName': 'b', 'jobArn': 'arn:aws:bedrock:r:a:evaluation-job/id-b',
             'outputDataConfig': {'s3Uri': 's3://bucket/b'}},
        ]
        assert output_filter.process(jobs) == [jobs[0]]
        client.get_bucket_location.assert_called_once_with(Bucket='bucket')
        client.get_bucket_tagging.assert_called_once_with(Bucket='bucket')
        client.get_bucket_versioning.assert_called_once_with(Bucket='bucket')
        client.get_bucket_lifecycle_configuration.assert_called_once_with(Bucket='bucket')
        assert not client.list_buckets.called

    def test_missing_bucket_from_s3_error(self):
        client = mock.MagicMock()
        client.meta.region_name = 'us-east-1'
        not_found = ClientError(
            {'Error': {'Code': 'NoSuchBucket', 'Message': 'missing'}},
            'GetBucketLocation')
        client.get_bucket_location.side_effect = not_found
        client.get_bucket_tagging.side_effect = not_found
        client.get_bucket_lifecycle_configuration.side_effect = not_found
        session = mock.MagicMock()
        session.client.return_value = client

        def session_factory():
            return session

        output_filter = self.get_filter(
            {'value': 'absent', 'op': 'eq'}, session_factory)
        job = {'outputDataConfig': {'s3Uri': 's3://missing/evaluations/'}}
        assert output_filter.process([job]) == [job]
        bucket = job['c7n:OutputBucket']
        assert bucket['c7n:BedrockEvaluationOutput']['Error'] == 'bucket-not-found'
        assert 'c7n:BedrockOutputBucketError' not in bucket

    def test_missing_bucket_after_location_from_s3_error(self):
        client = mock.MagicMock()
        client.meta.region_name = 'us-east-1'
        not_found = ClientError(
            {'Error': {'Code': 'NoSuchBucket', 'Message': 'missing'}},
            'GetBucketLifecycleConfiguration')
        client.get_bucket_location.return_value = {'LocationConstraint': None}
        client.get_bucket_tagging.return_value = {'TagSet': []}
        client.get_bucket_lifecycle_configuration.side_effect = not_found
        session = mock.MagicMock()
        session.client.return_value = client

        def session_factory():
            return session

        output_filter = self.get_filter(
            {'value': 'absent', 'op': 'eq'}, session_factory)
        job = {'outputDataConfig': {'s3Uri': 's3://missing/evaluations/'}}
        assert output_filter.process([job]) == [job]
        bucket = job['c7n:OutputBucket']
        assert bucket['Location'] == {'LocationConstraint': None}
        assert bucket['Tags'] == []
        assert bucket['c7n:BedrockEvaluationOutput']['Error'] == 'bucket-not-found'
        assert 'c7n:BedrockOutputBucketError' not in bucket

    def test_no_s3_calls_without_output_bucket_filter(self):
        bedrock = mock.MagicMock()
        bedrock.list_evaluation_jobs.return_value = {'jobSummaries': []}
        services = []
        session = mock.MagicMock()

        def client(service, *args, **kwargs):
            services.append(service)
            return bedrock

        session.client.side_effect = client

        def session_factory():
            return session

        policy = self.load_policy(
            {'name': 'bedrock-evaluation-no-output-filter',
             'resource': 'bedrock-evaluation-job'},
            session_factory=session_factory,
            config={'region': 'us-east-1'},
        )
        with mock.patch('c7n.resources.bedrock.BucketAssembly') as assembly:
            assert policy.run() == []
            assembly.assert_not_called()
        assert 's3' not in services

    def test_permissions_and_validation(self):
        default = self.get_filter()
        assert set(default.get_permissions()) == {
            's3:GetBucketLocation', 's3:GetBucketTagging',
            's3:GetLifecycleConfiguration', 's3:GetBucketVersioning'}

        with pytest.raises(PolicyValidationError):
            self.get_filter({'key': 'Versioning.Status', 'value': 'Enabled'})


@terraform('bedrock_evaluation_job', scope='function')
def test_bedrock_evaluation_job(test, bedrock_evaluation_job):
    session_factory = test.replay_flight_data('bedrock_evaluation_job')
    job_name = bedrock_evaluation_job.outputs['job_name']['value']
    output_s3_uri = bedrock_evaluation_job.outputs['output_s3_uri']['value']

    policy = test.load_policy(
        {
            'name': 'bedrock-evaluation-job',
            'resource': 'bedrock-evaluation-job',
            'filters': [
                {'jobName': job_name},
                {'tag:Owner': 'c7n'},
            ],
        },
        session_factory=session_factory,
        config={'region': 'us-east-1'},
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['jobName'] == job_name
    assert resources[0]['outputDataConfig']['s3Uri'] == output_s3_uri
    assert resources[0]['jobArn'].startswith('arn:aws:bedrock:')
    assert resources[0]['status'] in ('InProgress', 'Completed')
    assert {'Key': 'Owner', 'Value': 'c7n'} in resources[0]['Tags']


@terraform('bedrock_evaluation_job', scope='function')
def test_bedrock_evaluation_job_output_retention(test, bedrock_evaluation_job):
    session_factory = test.replay_flight_data('bedrock_evaluation_job_output_bucket')
    job_name = bedrock_evaluation_job.outputs['job_name']['value']
    output_s3_uri = bedrock_evaluation_job.outputs['output_s3_uri']['value']
    bucket_name = output_s3_uri.split('/', 3)[2]

    def load_policy(op, value):
        return test.load_policy(
            {
                'name': 'bedrock-evaluation-job-output-retention-%s' % op,
                'resource': 'bedrock-evaluation-job',
                'filters': [
                    {'jobName': job_name},
                    {
                        'type': 'output-retention',
                        'key': (
                            '"c7n:BedrockEvaluationOutput".'
                            'EffectiveExpirationDays'),
                        'op': op,
                        'value': value,
                    },
                ],
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'},
        )

    resources = load_policy('gt', 20).run()
    assert len(resources) == 1
    bucket = resources[0]['c7n:OutputBucket']
    output = bucket['c7n:BedrockEvaluationOutput']
    assert bucket['Name'] == bucket_name
    assert bucket['Versioning']['Status'] == 'Enabled'
    assert output['S3Uri'] == output_s3_uri
    assert output['Prefix'] == 'evaluations/'
    assert output['ArtifactPrefix'] == (
        'evaluations/%s/%s/' % (job_name, resources[0]['jobArn'].rsplit('/', 1)[-1]))
    assert output['EffectiveExpirationDays'] == 40
    assert output['Error'] is None
    assert [r['ID'] for r in output['PrefixMatchedLifecycleRules']] == [
        'evaluation-output-retention']

    assert load_policy('lt', 40).run() == []


@terraform('bedrock_evaluation_job', scope='function')
def test_bedrock_evaluation_job_tag_actions(test, bedrock_evaluation_job):
    session_factory = test.replay_flight_data('bedrock_evaluation_job_tag_actions')
    client = session_factory().client('bedrock')
    job_name = bedrock_evaluation_job.outputs['job_name']['value']

    policy = test.load_policy(
        {
            'name': 'bedrock-evaluation-job-tag',
            'resource': 'bedrock-evaluation-job',
            'filters': [
                {'jobName': job_name},
                {'tag:TestTag': 'absent'},
            ],
            'actions': [
                {'type': 'tag', 'key': 'TestTag', 'value': 'TestValue'},
            ],
        },
        session_factory=session_factory,
        config={'region': 'us-east-1'},
    )

    resources = policy.run()
    assert len(resources) == 1
    job_arn = resources[0]['jobArn']
    tags = client.list_tags_for_resource(resourceARN=job_arn)['tags']
    assert {'key': 'TestTag', 'value': 'TestValue'} in tags

    policy = test.load_policy(
        {
            'name': 'bedrock-evaluation-job-remove-tag',
            'resource': 'bedrock-evaluation-job',
            'filters': [
                {'jobName': job_name},
                {'tag:TestTag': 'present'},
            ],
            'actions': [
                {'type': 'remove-tag', 'tags': ['TestTag']},
            ],
        },
        session_factory=session_factory,
        config={'region': 'us-east-1'},
    )

    resources = policy.run()
    assert len(resources) == 1
    tags = client.list_tags_for_resource(resourceARN=job_arn)['tags']
    assert 'TestTag' not in {t['key'] for t in tags}
    assert {'key': 'Owner', 'value': 'c7n'} in tags


@terraform('bedrock_guardrail')
def test_bedrock_guardrail(test, bedrock_guardrail):
    session_factory = test.replay_flight_data('test_bedrock_guardrail')
    test.assertNotEqual(
        bedrock_guardrail[
            'aws_bedrock_guardrail.test_guardrail.guardrail_arn'
        ],
        None,
    )
    p = test.load_policy(
        {
            'name': 'bedrock-guardrail-test',
            'resource': 'bedrock-guardrail',
        }, session_factory=session_factory
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)
    test.assertIn('Tags', resources[0])
    test.assertEqual(
        resources[0]['arn'],
        bedrock_guardrail[
            'aws_bedrock_guardrail.test_guardrail.guardrail_arn'
        ],
    )


@terraform('bedrock_guardrail')
def test_bedrock_guardrail_absent_policy(test, bedrock_guardrail):
    session_factory = test.replay_flight_data('test_bedrock_guardrail_absent_policy')
    test.assertNotEqual(
        bedrock_guardrail[
            'aws_bedrock_guardrail.test_guardrail.guardrail_arn'
        ],
        None,
    )

    content_policy = test.load_policy(
        {
            'name': 'bedrock-guardrail-missing-content-policy',
            'resource': 'bedrock-guardrail',
            'filters': [
                {'type': 'value', 'key': 'contentPolicy', 'value': 'absent'},
            ],
        }, session_factory=session_factory
    )
    resources_missing_content_policy = content_policy.run()
    test.assertEqual(len(resources_missing_content_policy), 0)

    word_policy = test.load_policy(
        {
            'name': 'bedrock-guardrail-missing-word-policy',
            'resource': 'bedrock-guardrail',
            'filters': [
                {'type': 'value', 'key': 'wordPolicy', 'value': 'absent'},
            ],
        }, session_factory=session_factory
    )
    resource_missing_word_policy = word_policy.run()
    test.assertEqual(len(resource_missing_word_policy), 1)


@terraform('bedrock_guardrail_tag_actions')
def test_bedrock_guardrail_tag_actions(test, bedrock_guardrail_tag_actions):
    session_factory = test.replay_flight_data('test_bedrock_guardrail_tag_actions')
    client = session_factory().client('bedrock')
    test.assertNotEqual(
        bedrock_guardrail_tag_actions[
            'aws_bedrock_guardrail.test_guardrail.guardrail_arn'
        ],
        None,
    )

    guardrail_arn = (
        bedrock_guardrail_tag_actions[
            'aws_bedrock_guardrail.test_guardrail.guardrail_arn'
        ]
    )

    # Test adding tags
    p = test.load_policy(
        {
            'name': 'bedrock-app-guardrail-tag',
            'resource': 'bedrock-guardrail',
            'filters': [
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
    tags = client.list_tags_for_resource(resourceARN=guardrail_arn)['tags']
    tag_dict = {t['key']: t['value'] for t in tags}
    test.assertEqual(tag_dict['NewTag'], 'NewValue')
    test.assertEqual(tag_dict['AnotherTag'], 'AnotherValue')
    test.assertEqual(tag_dict['Environment'], 'test')  # Original tag still there

    # Test removing tags
    p = test.load_policy(
        {
            'name': 'bedrock-app-guardrail-untag',
            'resource': 'bedrock-guardrail',
            'filters': [
                {'guardrailArn': guardrail_arn},
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
    tags = client.list_tags_for_resource(resourceARN=guardrail_arn)['tags']
    tag_dict = {t['key']: t['value'] for t in tags}
    test.assertNotIn('AnotherTag', tag_dict)
    test.assertNotIn('Owner', tag_dict)
    test.assertEqual(tag_dict['NewTag'], 'NewValue')  # Still there
    test.assertEqual(tag_dict['Environment'], 'test')  # Still there


@terraform('bedrock_guardrail_update')
def test_bedrock_guardrail_update(test, bedrock_guardrail_update):
    session_factory = test.replay_flight_data('test_bedrock_guardrail_update')
    client = session_factory().client('bedrock')
    test.assertNotEqual(
        bedrock_guardrail_update[
            'aws_bedrock_guardrail.test_guardrail.guardrail_arn'
        ],
        None,
    )

    guardrail_arn = (
        bedrock_guardrail_update[
            'aws_bedrock_guardrail.test_guardrail.guardrail_arn'
        ]
    )

    p = test.load_policy(
        {
            'name': 'bedrock-app-guardrail-tag',
            'resource': 'bedrock-guardrail',
            'filters': [
                {'type': 'value', 'key': 'wordPolicy', 'value': 'absent'},
            ],
            'actions': [
                {
                    'type': 'update',
                    'wordPolicyConfig': {
                        'wordsConfig': [
                            {
                                'text': 'HATE',
                                'inputAction': 'BLOCK',
                                'outputAction': 'NONE',
                                'inputEnabled': True,
                                'outputEnabled': False,
                            }
                        ],
                        'managedWordListsConfig': [
                            {
                                'type': 'PROFANITY',
                                'inputAction': 'BLOCK',
                                'outputAction': 'NONE',
                                'inputEnabled': True,
                                'outputEnabled': False,
                            }
                        ],
                    },
                }
            ],
        },
        session_factory=session_factory,
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)

    # Verify policy was added
    word_policy = client.get_guardrail(guardrailIdentifier=guardrail_arn)['wordPolicy']
    test.assertEqual(word_policy['words'][0]['text'], 'HATE')
    test.assertEqual(word_policy['managedWordLists'][0]['type'], 'PROFANITY')


@terraform('bedrock_inference_profile_token_metrics')
def test_bedrock_inference_profile_token_metrics(
        test, bedrock_inference_profile_token_metrics):
    profile_arn = bedrock_inference_profile_token_metrics.outputs[
        'inference_profile_arn']['value']

    session_factory = test.replay_flight_data(
        'bedrock_inference_profile_token_metrics', region='us-east-1')

    def run_metric_policy(metric_name, value=0, statistics='Sum'):
        metric_filter = {
            'type': 'metrics',
            'name': metric_name,
            'days': 1,
            'period': 300,
            'value': value,
            'op': 'greater-than',
        }
        if statistics is not None:
            metric_filter['statistics'] = statistics
        policy = test.load_policy(
            {
                'name': 'bedrock-inference-profile-token-metrics',
                'resource': 'aws.bedrock-inference-profile',
                'filters': [
                    {'inferenceProfileArn': profile_arn},
                    metric_filter,
                ],
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'},
        )
        return policy, policy.run()

    for metric_name in ('InputTokenCount', 'OutputTokenCount'):
        _, resources = run_metric_policy(metric_name)
        assert len(resources) == 1
        assert resources[0]['inferenceProfileArn'] == profile_arn
        annotation_key = 'AWS/Bedrock.%s.Sum.1' % metric_name
        assert annotation_key in resources[0]['c7n.metrics']
        assert max(
            point['Sum'] for point in resources[0]['c7n.metrics'][annotation_key]
        ) > 0

    total_policy, resources = run_metric_policy('c7n:TotalTokenCount', statistics=None)
    assert len(resources) == 1
    assert resources[0]['inferenceProfileArn'] == profile_arn
    total_key = 'AWS/Bedrock.c7n:TotalTokenCount.Sum.1'
    assert total_key in resources[0]['c7n.metrics']
    observed_total = max(
        point['Sum'] for point in resources[0]['c7n.metrics'][total_key])
    assert observed_total > 0
    assert 'cloudwatch:GetMetricData' in total_policy.get_permissions()
    assert 'cloudwatch:GetMetricStatistics' not in total_policy.get_permissions()

    _, resources = run_metric_policy('c7n:TotalTokenCount', value=observed_total + 1)
    assert resources == []


def test_bedrock_inference_profile_bad_statistics(test):
    with pytest.raises(
        PolicyValidationError, match="c7n:TotalTokenCount only supports the Sum statistic"
    ):
        test.load_policy(
            {
                'name': 'bedrock-inference-profile-invalid-total-statistic',
                'resource': 'aws.bedrock-inference-profile',
                'filters': [{
                    'type': 'metrics',
                    'name': 'c7n:TotalTokenCount',
                    'statistics': 'Average',
                    'value': 0,
                }],
            },
        )
