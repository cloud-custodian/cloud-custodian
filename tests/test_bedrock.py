# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import logging
import time

import boto3
import pytest

from unittest import mock
from .common import ACCOUNT_ID, BaseTest, event_data
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from pytest_terraform import terraform
from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.resources.bedrock import (
    KnowledgeBaseRetrievalActivity, count_retrievals, get_bedrock_output_artifact_prefix,
    get_bedrock_output_lifecycle, parse_bedrock_output_s3_uri, parse_log_group_arn,
    records_all_knowledge_base_events)
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

    def test_bedrock_custom_model_deployments_filter_schema(self):
        session_factory = self.replay_flight_data('test_bedrock_custom_model')
        p = self.load_policy(
            {
                'name': 'bedrock-custom-model-no-active-deployment',
                'resource': 'bedrock-custom-model',
                'filters': [
                    {'type': 'deployments', 'status': 'Active', 'value': 'absent'},
                ],
            },
            session_factory=session_factory,
        )
        self.assertTrue(p)

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


# A long-lived model, not built per test run -- fine-tuning takes hours. Found
# by name, since a rebuild changes its ARN.
# See tests/terraform/bedrock_deployable_custom_model.
DEPLOYABLE_CUSTOM_MODEL_NAME = "KEEP-c7n-deployable-test-fixture"
DEPLOYABLE_CUSTOM_MODEL_REGION = "us-west-2"


def wait_for_custom_model_deployment_active(client, deployment_arn, test):
    status = None
    for _ in range(60):
        status = client.get_custom_model_deployment(
            customModelDeploymentIdentifier=deployment_arn)['status']
        if status == 'Active':
            return
        if status == 'Failed':
            raise RuntimeError(f'custom model deployment {deployment_arn} failed')
        if test.recording:
            time.sleep(20)
    raise RuntimeError(
        f'custom model deployment {deployment_arn} did not become Active: {status}')


@pytest.fixture
def create_custom_model_deployment(test):
    """Create an on-demand custom model deployment, and clean it up after.

    Not a Terraform fixture: the AWS provider has no deployment resource.

    Yields ``(model_arn, region) -> deployment_arn``. Set
    ``test.session_factory`` first, so its calls record with the test.
    """
    created = []

    def _create(model_arn, region, name="c7n-test-custom-model-deployment"):
        client = test.session_factory().client('bedrock', region_name=region)
        deployment_arn = client.create_custom_model_deployment(
            modelDeploymentName=name, modelArn=model_arn)['customModelDeploymentArn']
        created.append((client, deployment_arn))
        wait_for_custom_model_deployment_active(client, deployment_arn, test)
        return deployment_arn

    try:
        yield _create
    finally:
        for client, deployment_arn in created:
            try:
                client.delete_custom_model_deployment(
                    customModelDeploymentIdentifier=deployment_arn)
            except client.exceptions.ResourceNotFoundException:
                pass


def test_bedrock_custom_model_deployments_filter(test, create_custom_model_deployment):
    test.session_factory = test.replay_flight_data(
        'test_bedrock_custom_model_deployments_filter',
        region=DEPLOYABLE_CUSTOM_MODEL_REGION)

    # CreateCustomModelDeployment needs the ARN; GetCustomModel takes the name.
    client = test.session_factory().client(
        'bedrock', region_name=DEPLOYABLE_CUSTOM_MODEL_REGION)
    model_arn = client.get_custom_model(
        modelIdentifier=DEPLOYABLE_CUSTOM_MODEL_NAME)['modelArn']

    create_custom_model_deployment(model_arn, DEPLOYABLE_CUSTOM_MODEL_REGION)

    # Unscoped, as a real policy would be.
    present = test.load_policy(
        {
            'name': 'bedrock-custom-model-active-deployment',
            'resource': 'aws.bedrock-custom-model',
            'filters': [
                {'type': 'deployments', 'status': 'Active', 'value': 'present'},
            ],
        },
        session_factory=test.session_factory,
        config={'region': DEPLOYABLE_CUSTOM_MODEL_REGION},
    )
    resources = present.run()

    # Shared account, so other models may come and go -- only assert ours.
    assert any(r['modelName'] == DEPLOYABLE_CUSTOM_MODEL_NAME for r in resources)


def test_bedrock_custom_model_undeployed(test):
    # An Active model with no deployment: costs storage while serving nothing.
    test.session_factory = test.replay_flight_data(
        'test_bedrock_custom_model_undeployed',
        region=DEPLOYABLE_CUSTOM_MODEL_REGION)

    policy = test.load_policy(
        {
            'name': 'bedrock-custom-model-undeployed',
            'resource': 'aws.bedrock-custom-model',
            'filters': [
                {'type': 'deployments', 'status': 'Active', 'value': 'absent'},
            ],
        },
        session_factory=test.session_factory,
        config={'region': DEPLOYABLE_CUSTOM_MODEL_REGION},
    )
    resources = policy.run()

    assert any(r['modelName'] == DEPLOYABLE_CUSTOM_MODEL_NAME for r in resources)


class BedrockMantleProject(BaseTest):

    def test_bedrock_mantle_project_query(self):
        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_mantle_project_query', region='us-east-1')
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_mantle_project_query', region='us-east-1')
        p = self.load_policy(
            {
                'name': 'mantle-project-tagged',
                'resource': 'aws.bedrock-mantle-project',
                'filters': [{'tag:Owner': 'c7n'}],
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['Arn'].startswith(
            'arn:aws:bedrock-mantle:us-east-1:'))
        self.assertTrue(resources[0]['Id'].startswith('proj_'))
        tags = {t['Key']: t['Value'] for t in resources[0]['Tags']}
        self.assertEqual(tags['Owner'], 'c7n')

    def test_bedrock_mantle_project_untagged(self):
        # the account default project carries no tags; the tagging
        # api augment must still set an empty Tags list so absent
        # tag filters match rather than error.
        if C7N_FUNCTIONAL:
            session_factory = self.record_flight_data(
                'test_bedrock_mantle_project_untagged', region='us-east-1')
        else:
            session_factory = self.replay_flight_data(
                'test_bedrock_mantle_project_untagged', region='us-east-1')
        p = self.load_policy(
            {
                'name': 'mantle-project-untagged',
                'resource': 'aws.bedrock-mantle-project',
                'filters': [
                    {'Id': 'default'},
                    {'tag:Owner': 'absent'},
                ],
            },
            session_factory=session_factory,
            config={'region': 'us-east-1'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Tags'], [])
        self.assertEqual(
            sorted(p.get_permissions()),
            ['bedrock-mantle:ListProjects',
             'bedrock-mantle:ListTagsForResource',
             'cloudformation:ListResources',
             'tag:GetResources'])


def knowledge_base_selector(*extra_conditions):
    return {'FieldSelectors': [
        {'Field': 'eventCategory', 'Equals': ['Data']},
        {'Field': 'resources.type', 'Equals': ['AWS::Bedrock::KnowledgeBase']},
        *extra_conditions,
    ]}


@pytest.mark.parametrize('selectors, expected', [
    pytest.param(
        {'AdvancedEventSelectors': [knowledge_base_selector()]}, True,
        id='exact'),
    pytest.param(
        {'AdvancedEventSelectors': [
            {'FieldSelectors': [{'Field': 'eventCategory', 'Equals': ['Management']}]},
            knowledge_base_selector(),
        ]}, True,
        id='beside-management-events'),
    pytest.param(
        {'AdvancedEventSelectors': [
            knowledge_base_selector({'Field': 'readOnly', 'Equals': ['true']})]}, False,
        id='read-only-condition'),
    pytest.param(
        {'AdvancedEventSelectors': [knowledge_base_selector(
            {'Field': 'resources.ARN', 'StartsWith': [
                'arn:aws:bedrock:us-east-1:123456789012:knowledge-base/ABCDEFGHIJ']})]}, False,
        id='one-knowledge-base-only'),
    pytest.param(
        {'AdvancedEventSelectors': [{'FieldSelectors': [
            {'Field': 'eventCategory', 'Equals': ['Data']},
            {'Field': 'resources.type', 'Equals': ['AWS::Bedrock::AgentAlias']},
        ]}]}, False,
        id='other-resource-type'),
    pytest.param(
        {'AdvancedEventSelectors': [{'FieldSelectors': [
            {'Field': 'eventCategory', 'Equals': ['Data']},
            {'Field': 'resources.type', 'Equals': ['AWS::Bedrock::KnowledgeBase'],
             'NotEquals': ['AWS::Bedrock::KnowledgeBase']},
        ]}]}, False,
        id='extra-operator'),
    pytest.param(
        {'EventSelectors': [{'ReadWriteType': 'All', 'IncludeManagementEvents': True}]}, False,
        id='basic-selectors-only'),
])
def test_records_all_knowledge_base_events(selectors, expected):
    assert records_all_knowledge_base_events(selectors) is expected


@pytest.mark.parametrize('arn, expected', [
    pytest.param(
        'arn:aws:logs:us-east-2:123456789012:log-group:/aws/cloudtrail/kb:*',
        ('123456789012', 'us-east-2', '/aws/cloudtrail/kb'),
        id='trail-format-with-leading-slash'),
    pytest.param(
        'arn:aws:logs:us-west-2:123456789012:log-group:kb-events',
        ('123456789012', 'us-west-2', 'kb-events'),
        id='plain'),
])
def test_parse_log_group_arn(arn, expected):
    assert parse_log_group_arn(arn) == expected


@pytest.mark.parametrize('arn', [
    pytest.param('arn:aws:logs:us-east-1:123456789012:log-group', id='no-name'),
    pytest.param('arn:aws:cloudtrail:us-east-1:123456789012:trail/kb', id='not-a-log-group'),
])
def test_parse_log_group_arn_rejects(arn):
    with pytest.raises(ValueError):
        parse_log_group_arn(arn)


KB_ARN = 'arn:aws:bedrock:us-east-1:123456789012:knowledge-base/ABCDEFGHIJ'
RESULT_ROW = [{'field': 'resources.0.ARN', 'value': KB_ARN}, {'field': 'retrievals', 'value': '4'}]


def test_count_retrievals():
    rows = [RESULT_ROW, [{'field': 'retrievals', 'value': '2'}]]
    assert count_retrievals(rows) == {KB_ARN: 4}


def retrieval_activity_policy_data(**filter_data):
    return {
        'name': 'bedrock-knowledge-base-retrieval-activity',
        'resource': 'aws.bedrock-knowledge-base',
        'filters': [{'type': 'retrieval-activity', 'source': 'cloudwatch-logs', **filter_data}],
    }


@pytest.mark.parametrize('filter_data', [
    pytest.param({'source': 'cloudtrail-lake'}, id='unknown-source'),
    pytest.param(
        {'log-group': 'arn:aws:logs:us-east-1:123456789012:log-group'}, id='bad-log-group-arn'),
])
def test_retrieval_activity_rejects_invalid_policy(test, filter_data):
    with pytest.raises(PolicyValidationError):
        test.load_policy(retrieval_activity_policy_data(**filter_data), validate=True)


def test_retrieval_activity_permissions(test):
    policy = test.load_policy(retrieval_activity_policy_data())
    assert {
        'cloudtrail:DescribeTrails', 'cloudtrail:GetEventSelectors', 'cloudtrail:GetTrailStatus',
        'logs:DescribeLogGroups', 'logs:StartQuery', 'logs:GetQueryResults', 'logs:StopQuery',
    } <= policy.get_permissions()


def retrieval_activity_filter(test, cache=False, **filter_data):
    policy = test.load_policy(
        retrieval_activity_policy_data(**filter_data),
        config={'region': 'us-east-1', 'account_id': ACCOUNT_ID}, cache=cache)
    activity = policy.resource_manager.filters[0]
    activity.poll_delay = 0
    activity.poll_max_attempts = 3
    return activity


def use_logs_client(monkeypatch, logs):
    """Hand the filter this logs client, and return the regions it asked for."""
    regions = []

    def client(service, region_name):
        regions.append(region_name)
        return logs

    monkeypatch.setattr(
        'c7n.resources.bedrock.local_session',
        lambda session_factory: mock.Mock(client=client))
    return regions


def query_statuses(*statuses, results=()):
    """A logs client that returns one query status per get_query_results call."""
    client = mock.Mock()
    client.get_query_results.side_effect = [
        {'status': status, 'results': list(results) if status == 'Complete' else []}
        for status in statuses]
    return client


def test_retrieval_activity_query_request(test, monkeypatch):
    logs = boto3.client('logs', region_name='us-east-1')
    stubber = Stubber(logs)
    stubber.add_response('start_query', {'queryId': 'query-1'}, {
        'logGroupName': 'kb-events',
        'startTime': 1_000_000_000 - 30 * 86400,
        'endTime': 1_000_000_000,
        'queryString': (
            'filter eventSource = "bedrock.amazonaws.com" and eventName = "Retrieve"'
            ' | stats count(*) as retrievals by resources.0.ARN'),
    })
    stubber.add_response(
        'get_query_results', {'status': 'Complete', 'results': [RESULT_ROW]},
        {'queryId': 'query-1'})
    activity = retrieval_activity_filter(test, days=30)
    regions = use_logs_client(monkeypatch, logs)
    monkeypatch.setattr(time, 'time', lambda: 1_000_000_000)

    with stubber:
        assert activity.query_log_group('us-east-2', 'kb-events') == {KB_ARN: 4}
    stubber.assert_no_pending_responses()
    # The log group's region, not the policy's (us-east-1).
    assert regions == ['us-east-2']


def test_retrieval_activity_retries_query_limit(test, monkeypatch):
    logs = boto3.client('logs', region_name='us-east-1')
    stubber = Stubber(logs)
    stubber.add_client_error('start_query', 'LimitExceededException')
    stubber.add_response('start_query', {'queryId': 'query-1'})
    stubber.add_response('get_query_results', {'status': 'Complete', 'results': [RESULT_ROW]})
    activity = retrieval_activity_filter(test)
    use_logs_client(monkeypatch, logs)
    monkeypatch.setattr(time, 'sleep', lambda seconds: None)

    with stubber:
        assert activity.query_log_group('us-east-1', 'kb-events') == {KB_ARN: 4}
    stubber.assert_no_pending_responses()


def test_retrieval_activity_caches_counts(test, monkeypatch):
    logs = boto3.client('logs', region_name='us-east-1')
    stubber = Stubber(logs)
    stubber.add_response('start_query', {'queryId': 'query-1'})
    stubber.add_response('get_query_results', {'status': 'Complete', 'results': [RESULT_ROW]})
    activity = retrieval_activity_filter(test, cache=True)
    use_logs_client(monkeypatch, logs)

    with stubber:
        first = activity.query_log_group('us-east-1', 'kb-events')
        # A second region's run reads the same log group: no second query.
        second = activity.query_log_group('us-east-1', 'kb-events')
    assert first == second == {KB_ARN: 4}
    stubber.assert_no_pending_responses()


def test_retrieval_activity_cache_key_includes_days(test, monkeypatch):
    logs = boto3.client('logs', region_name='us-east-1')
    stubber = Stubber(logs)
    for query_id in ('query-30', 'query-60'):
        stubber.add_response('start_query', {'queryId': query_id})
        stubber.add_response('get_query_results', {'status': 'Complete', 'results': []})
    activity = retrieval_activity_filter(test, cache=True, days=30)
    use_logs_client(monkeypatch, logs)

    with stubber:
        activity.query_log_group('us-east-1', 'kb-events')
        activity.data['days'] = 60
        activity.query_log_group('us-east-1', 'kb-events')
    stubber.assert_no_pending_responses()


def test_retrieval_activity_describe_log_group_exact_name(test, monkeypatch):
    logs = boto3.client('logs', region_name='us-east-1')
    stubber = Stubber(logs)
    stubber.add_response('describe_log_groups', {'logGroups': [
        {'logGroupName': 'kb-events-archive', 'retentionInDays': 1},
        {'logGroupName': 'kb-events', 'retentionInDays': 30},
    ]}, {'logGroupNamePrefix': 'kb-events'})
    activity = retrieval_activity_filter(test)
    regions = use_logs_client(monkeypatch, logs)

    with stubber:
        assert activity.describe_log_group('us-east-2', 'kb-events') == {
            'logGroupName': 'kb-events', 'retentionInDays': 30}
    assert regions == ['us-east-2']


def test_retrieval_activity_query_completes(test):
    client = query_statuses('Scheduled', 'Running', 'Complete', results=[RESULT_ROW])
    assert retrieval_activity_filter(test).wait_for_query(client, 'query-1') == [RESULT_ROW]
    assert client.get_query_results.call_count == 3
    client.stop_query.assert_not_called()


def test_retrieval_activity_query_fails(test):
    with pytest.raises(PolicyExecutionError, match='ended Failed'):
        retrieval_activity_filter(test).wait_for_query(
            query_statuses('Running', 'Failed'), 'query-1')


def test_retrieval_activity_query_times_out(test):
    client = query_statuses('Running', 'Running', 'Running')
    client.stop_query.side_effect = ClientError(
        {'Error': {'Code': 'InvalidParameterException', 'Message': 'query already ended'}},
        'StopQuery')
    # The stop_query error must not hide the timeout.
    with pytest.raises(PolicyExecutionError, match='did not finish'):
        retrieval_activity_filter(test).wait_for_query(client, 'query-1')
    client.stop_query.assert_called_once_with(queryId='query-1')


def test_retrieval_activity_query_more_pages(test):
    client = mock.Mock()
    client.get_query_results.return_value = {
        'status': 'Complete', 'results': [RESULT_ROW], 'nextToken': 'more'}
    with pytest.raises(PolicyExecutionError, match='more than'):
        retrieval_activity_filter(test).wait_for_query(client, 'query-1')


def test_retrieval_activity_query_row_limit(test):
    activity = retrieval_activity_filter(test)
    activity.max_query_rows = 2
    with pytest.raises(PolicyExecutionError, match='more than 2 rows'):
        activity.wait_for_query(
            query_statuses('Complete', results=[RESULT_ROW, RESULT_ROW]), 'query-1')


def test_retrieval_activity_trail_discovery(test, monkeypatch, caplog):
    started = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def trail(name, account=ACCOUNT_ID, log_group=True, writes_to=None):
        t = {'Name': name, 'TrailARN': f'arn:aws:cloudtrail:us-east-1:{account}:trail/{name}'}
        if log_group:
            t['CloudWatchLogsLogGroupArn'] = (
                f'arn:aws:logs:us-east-1:{account}:log-group:{writes_to or name}-events:*')
        return t

    trails = {t['Name']: t for t in (
        trail('no-log-group', log_group=False),
        trail('organization', account='111111111111'),
        trail('read-only'),
        trail('stopped'),
        trail('delivery-error'),
        trail('qualifies'),
        trail('qualifies-later', writes_to='qualifies'),
    )}
    selectors = {
        t['TrailARN']: {'AdvancedEventSelectors': [knowledge_base_selector()]}
        for t in trails.values()}
    selectors[trails['read-only']['TrailARN']] = {'AdvancedEventSelectors': [
        knowledge_base_selector({'Field': 'readOnly', 'Equals': ['true']})]}
    statuses = {
        t['TrailARN']: {'IsLogging': True, 'StartLoggingTime': started} for t in trails.values()}
    statuses[trails['stopped']['TrailARN']]['IsLogging'] = False
    statuses[trails['delivery-error']['TrailARN']]['LatestCloudWatchLogsDeliveryError'] = (
        'AccessDenied')
    statuses[trails['qualifies-later']['TrailARN']]['StartLoggingTime'] = (
        datetime(2026, 9, 20, tzinfo=timezone.utc))

    client = mock.Mock()
    client.get_event_selectors.side_effect = lambda TrailName: selectors[TrailName]
    client.get_trail_status.side_effect = lambda Name: statuses[Name]
    activity = retrieval_activity_filter(test)
    activity.manager.get_resource_manager = (
        lambda name: mock.Mock(resources=lambda: list(trails.values())))
    monkeypatch.setattr(
        'c7n.resources.bedrock.get_trail_groups',
        lambda session_factory, trails: {'us-east-1': (client, trails)})

    with caplog.at_level(logging.WARNING):
        # Two trails write to one log group: its history starts with the earlier one.
        assert activity.get_trail_log_groups() == {
            (ACCOUNT_ID, 'us-east-1', 'qualifies-events'): started.timestamp()}
    assert 'skipping trail delivery-error' in caplog.text
    # Trails without a log group, or owned by another account, cost no API calls.
    asked = str(client.get_event_selectors.call_args_list)
    assert 'no-log-group' not in asked and 'organization' not in asked


def test_retrieval_activity_requires_account_id(test):
    policy = test.load_policy(retrieval_activity_policy_data(), config={'region': 'us-east-1'})
    with pytest.raises(PolicyExecutionError, match='account ID is unknown'):
        policy.resource_manager.filters[0].get_trail_log_groups()


NOW = 2_000_000_000
DAY = 86400
KB_EVENTS = (ACCOUNT_ID, 'us-east-1', 'kb-events')


def log_group(name, created_days_ago=60, retention=None):
    description = {'logGroupName': name, 'creationTime': (NOW - created_days_ago * DAY) * 1000}
    if retention is not None:
        description['retentionInDays'] = retention
    return description


def choose_log_groups(test, monkeypatch, log_groups, trail_log_groups=None, **filter_data):
    """Run log group selection against stand-in trails and log groups."""
    if trail_log_groups is None:
        trail_log_groups = {KB_EVENTS: NOW - 60 * DAY}
    activity = retrieval_activity_filter(test, **filter_data)
    activity.get_trail_log_groups = lambda: trail_log_groups
    activity.describe_log_group = lambda region, name: log_groups.get(name)
    monkeypatch.setattr(time, 'time', lambda: NOW)
    return activity.get_log_groups()


@pytest.mark.parametrize('retention', [
    pytest.param(None, id='never-expires'),
    pytest.param(30, id='exactly-days'),
])
def test_retrieval_activity_keeps_log_group(test, monkeypatch, retention):
    log_groups = {'kb-events': log_group('kb-events', retention=retention)}
    assert choose_log_groups(test, monkeypatch, log_groups, days=30) == [('us-east-1', 'kb-events')]


def test_retrieval_activity_log_group_in_another_region(test, monkeypatch):
    # A multi-region trail homed in us-east-2, seen from a us-east-1 policy.
    trail_log_groups = {(ACCOUNT_ID, 'us-east-2', 'kb-events'): NOW - 60 * DAY}
    activity = retrieval_activity_filter(test)
    activity.get_trail_log_groups = lambda: trail_log_groups
    activity.describe_log_group = (
        lambda region, name: log_group(name) if region == 'us-east-2' else None)
    monkeypatch.setattr(time, 'time', lambda: NOW)

    assert activity.get_log_groups() == [('us-east-2', 'kb-events')]


def test_retrieval_activity_skips_deleted_log_group(test, monkeypatch, caplog):
    trail_log_groups = {
        (ACCOUNT_ID, 'us-east-1', 'deleted'): NOW - 60 * DAY,
        KB_EVENTS: NOW - 60 * DAY,
    }
    with caplog.at_level(logging.WARNING):
        assert choose_log_groups(
            test, monkeypatch, {'kb-events': log_group('kb-events')}, trail_log_groups,
        ) == [('us-east-1', 'kb-events')]
    assert 'skipping log group deleted not found' in caplog.text


def test_retrieval_activity_raises_without_log_groups(test, monkeypatch):
    with pytest.raises(PolicyExecutionError, match='no log group holds every knowledge base'):
        choose_log_groups(test, monkeypatch, {}, trail_log_groups={})


def test_retrieval_activity_raises_inside_not(test):
    # Under `not`, matching nothing would match every knowledge base.
    policy = test.load_policy({
        'name': 'bedrock-knowledge-base-retrieval-activity',
        'resource': 'aws.bedrock-knowledge-base',
        'filters': [{'not': [{'type': 'retrieval-activity', 'op': 'gt', 'value': 0}]}],
    }, config={'region': 'us-east-1', 'account_id': ACCOUNT_ID})
    activity = policy.resource_manager.filters[0].filters[0]
    activity.get_trail_log_groups = lambda: {}

    with pytest.raises(PolicyExecutionError):
        policy.resource_manager.filter_resources(
            [{'knowledgeBaseId': 'ABCDEFGHIJ', 'knowledgeBaseArn': KB_ARN}])


@pytest.mark.parametrize('name', [
    pytest.param('kb-events', id='name-in-policy-region'),
    pytest.param(f'arn:aws:logs:us-east-1:{ACCOUNT_ID}:log-group:kb-events:*', id='arn'),
])
def test_retrieval_activity_explicit_log_group(test, monkeypatch, name):
    trail_log_groups = {
        KB_EVENTS: NOW - 60 * DAY,
        (ACCOUNT_ID, 'us-east-1', 'security-events'): NOW - 60 * DAY,
    }
    log_groups = {n: log_group(n) for n in ('kb-events', 'security-events')}
    assert choose_log_groups(
        test, monkeypatch, log_groups, trail_log_groups, **{'log-group': name},
    ) == [('us-east-1', 'kb-events')]


@pytest.mark.parametrize('name', [
    pytest.param('settings-changes', id='not-fed-by-a-qualifying-trail'),
    pytest.param('arn:aws:logs:us-east-1:111111111111:log-group:kb-events', id='other-account'),
])
def test_retrieval_activity_explicit_log_group_rejected(test, monkeypatch, name):
    with pytest.raises(PolicyExecutionError, match='does not receive every knowledge base'):
        choose_log_groups(
            test, monkeypatch, {'kb-events': log_group('kb-events')}, **{'log-group': name})


def test_retrieval_activity_explicit_log_group_short_retention(test, monkeypatch):
    with pytest.raises(PolicyExecutionError, match='fewer than 30 days'):
        choose_log_groups(
            test, monkeypatch, {'kb-events': log_group('kb-events', retention=7)},
            days=30, **{'log-group': 'kb-events'})


@pytest.mark.parametrize('created_days_ago, trail_started_days_ago, warned', [
    pytest.param(60, 60, False, id='full-history'),
    pytest.param(3, 60, True, id='new-log-group'),
    pytest.param(60, 3, True, id='new-trail'),
])
def test_retrieval_activity_short_history_warning(
        test, monkeypatch, caplog, created_days_ago, trail_started_days_ago, warned):
    trail_log_groups = {KB_EVENTS: NOW - trail_started_days_ago * DAY}
    log_groups = {'kb-events': log_group('kb-events', created_days_ago=created_days_ago)}
    with caplog.at_level(logging.WARNING):
        assert choose_log_groups(
            test, monkeypatch, log_groups, trail_log_groups, days=30,
        ) == [('us-east-1', 'kb-events')]
    assert ('may be low' in caplog.text) is warned


def test_retrieval_activity_takes_highest_count_across_log_groups(test):
    activity = retrieval_activity_filter(test, op='gt', value=0)
    activity.get_log_groups = lambda: [('us-east-1', 'first'), ('us-east-2', 'second')]
    counts = {'first': {KB_ARN: 2}, 'second': {KB_ARN: 5}}
    activity.query_log_group = lambda region, name: counts[name]

    matched = activity.process([{'knowledgeBaseArn': KB_ARN}])

    assert [r['c7n:RetrievalActivity'] for r in matched] == [5]


def retrieval_activity_flight_data(test, monkeypatch, name):
    session_factory = test.replay_flight_data(
        f'bedrock_knowledge_base_retrieval_activity_{name}', region='us-east-1')
    if not test.recording:
        monkeypatch.setattr(KnowledgeBaseRetrievalActivity, 'poll_delay', 0)
    return session_factory


def retrieval_activity_policy(test, session_factory, **filter_data):
    return test.load_policy(
        retrieval_activity_policy_data(**{'days': 1, **filter_data}),
        session_factory=session_factory,
        config={'region': 'us-east-1', 'account_id': test.account_id},
    )


@terraform('bedrock_knowledge_base_retrieval_activity', scope='session')
def test_bedrock_knowledge_base_retrieval_activity_idle(
        test, bedrock_knowledge_base_retrieval_activity, monkeypatch):
    outputs = bedrock_knowledge_base_retrieval_activity.outputs
    session_factory = retrieval_activity_flight_data(test, monkeypatch, 'idle')

    resources = retrieval_activity_policy(test, session_factory, op='eq', value=0).run()

    assert [r['knowledgeBaseArn'] for r in resources] == [
        outputs['idle_knowledge_base_arn']['value']]
    assert resources[0]['c7n:RetrievalActivity'] == 0


@terraform('bedrock_knowledge_base_retrieval_activity', scope='session')
def test_bedrock_knowledge_base_retrieval_activity_count(
        test, bedrock_knowledge_base_retrieval_activity, monkeypatch):
    outputs = bedrock_knowledge_base_retrieval_activity.outputs
    session_factory = retrieval_activity_flight_data(test, monkeypatch, 'count')

    resources = retrieval_activity_policy(test, session_factory, op='gt', value=0).run()

    counts = {r['knowledgeBaseArn']: r['c7n:RetrievalActivity'] for r in resources}
    used = outputs['used_knowledge_base_arn']['value']
    canary = outputs['canary_knowledge_base_arn']['value']
    assert set(counts) == {used, canary}
    # One direct Retrieve, plus the Retrieve that Bedrock runs inside the
    # RetrieveAndGenerate and RetrieveAndGenerateStream calls.
    assert counts[used] == 3
    assert counts[canary] > 0


@terraform('bedrock_knowledge_base_retrieval_activity', scope='session')
def test_bedrock_knowledge_base_retrieval_activity_short_retention(
        test, bedrock_knowledge_base_retrieval_activity, monkeypatch, caplog):
    session_factory = retrieval_activity_flight_data(test, monkeypatch, 'short_retention')
    policy = retrieval_activity_policy(test, session_factory, days=2, op='eq', value=0)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(PolicyExecutionError, match='no log group holds every knowledge base'):
            policy.run()
    assert 'kb-activity-default-8ddc keeps events for fewer than 2 days' in caplog.text


@terraform('bedrock_knowledge_base_retrieval_activity', scope='session')
def test_bedrock_knowledge_base_retrieval_activity_explicit_log_group(
        test, bedrock_knowledge_base_retrieval_activity, monkeypatch):
    outputs = bedrock_knowledge_base_retrieval_activity.outputs
    session_factory = retrieval_activity_flight_data(test, monkeypatch, 'explicit_log_group')

    resources = retrieval_activity_policy(
        test, session_factory, op='eq', value=0,
        **{'log-group': outputs['log_group_name']['value']}).run()

    assert [r['knowledgeBaseArn'] for r in resources] == [
        outputs['idle_knowledge_base_arn']['value']]


@terraform('bedrock_knowledge_base_retrieval_activity', scope='session')
def test_bedrock_knowledge_base_retrieval_activity_missing_log_group(
        test, bedrock_knowledge_base_retrieval_activity, monkeypatch):
    session_factory = retrieval_activity_flight_data(test, monkeypatch, 'missing_log_group')
    policy = retrieval_activity_policy(
        test, session_factory, **{'log-group': 'c7n-kb-activity-missing'})

    with pytest.raises(PolicyExecutionError, match='does not receive every knowledge base'):
        policy.run()
