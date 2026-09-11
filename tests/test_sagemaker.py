# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from unittest import mock

import pytest
from pytest_terraform import terraform

from .common import BaseTest

from c7n.filters.metrics import MetricsFilter
from c7n.resources.sagemaker import (
    SAGEMAKER_METRICS, SagemakerEndpoint, SagemakerJobQueryParser,
    CompilationJobQueryParser)
from c7n.exceptions import PolicyValidationError

import botocore.exceptions as b_exc


class TestNotebookInstance(BaseTest):

    def test_list_notebook_instances(self):
        session_factory = self.replay_flight_data("test_sagemaker_notebook_instances")
        p = self.load_policy(
            {
                "name": "list-sagemaker-notebooks",
                "resource": "sagemaker-notebook",
                "filters": [
                    {"type": "value", "key": "SubnetId", "value": "subnet-efbcccb7"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_tag_notebook_instances(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_tag_notebook_instances"
        )
        p = self.load_policy(
            {
                "name": "tag-sagemaker-notebooks",
                "resource": "sagemaker-notebook",
                "filters": [{"tag:Category": "absent"}],
                "actions": [{"type": "tag", "key": "Category", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["NotebookInstanceArn"])["Tags"]
        self.assertEqual(tags[0]["Value"], "TestValue")

    def test_remove_tag_notebook_instance(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_remove_tag_notebook_instances"
        )
        p = self.load_policy(
            {
                "name": "untag-sagemaker-notebooks",
                "resource": "sagemaker-notebook",
                "filters": [{"tag:Category": "TestValue"}],
                "actions": [{"type": "remove-tag", "tags": ["Category"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["NotebookInstanceArn"])["Tags"]
        self.assertEqual(len(tags), 0)

    def test_mark_for_op_notebook_instance(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_mark_for_op_notebook_instance"
        )
        p = self.load_policy(
            {
                "name": "sagemaker-notebooks-untagged-delete",
                "resource": "sagemaker-notebook",
                "filters": [
                    {"tag:Category": "absent"},
                    {"tag:custodian_cleanup": "absent"},
                    {"NotebookInstanceStatus": "InService"},
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "stop",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["NotebookInstanceArn"])["Tags"]
        self.assertTrue(tags[0]["Key"], "custodian_cleanup")

    def test_marked_for_op_notebook_instance(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_marked_for_op_notebook_instance"
        )
        p = self.load_policy(
            {
                "name": "sagemaker-notebooks-untagged-delete",
                "resource": "sagemaker-notebook",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "stop",
                        "skew": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_start_notebook_instance(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_start_notebook_instance"
        )
        p = self.load_policy(
            {
                "name": "start-sagemaker-notebook",
                "resource": "sagemaker-notebook",
                "actions": [{"type": "start"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        notebook = client.describe_notebook_instance(
            NotebookInstanceName=resources[0]["NotebookInstanceName"]
        )
        self.assertTrue(notebook["NotebookInstanceStatus"], "Pending")

    def test_stop_notebook_instance(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_stop_notebook_instance"
        )
        p = self.load_policy(
            {
                "name": "stop-invalid-sagemaker-notebook",
                "resource": "sagemaker-notebook",
                "filters": [{"tag:Category": "absent"}],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        notebook = client.describe_notebook_instance(
            NotebookInstanceName=resources[0]["NotebookInstanceName"]
        )
        self.assertTrue(notebook["NotebookInstanceStatus"], "Stopping")

    def test_delete_notebook_instance(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_delete_notebook_instance"
        )
        p = self.load_policy(
            {
                "name": "delete-unencrypted-sagemaker-notebook",
                "resource": "sagemaker-notebook",
                "filters": [{"KmsKeyId": "empty"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        notebook = client.describe_notebook_instance(
            NotebookInstanceName=resources[0]["NotebookInstanceName"]
        )
        self.assertTrue(notebook["NotebookInstanceStatus"], "Deleting")

    def test_notebook_subnet(self):
        nb = "c7n-test-nb"
        session_factory = self.replay_flight_data(
            "test_sagemaker_notebook_subnet_filter"
        )
        p = self.load_policy(
            {
                "name": "sagemaker-notebook",
                "resource": "sagemaker-notebook",
                "filters": [{"type": "subnet", "key": "tag:Name", "value": "Pluto"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["NotebookInstanceName"], nb)

    def test_notebook_security_group(self):
        nb = "c7n-test-nb"
        session_factory = self.replay_flight_data(
            "test_sagemaker_notebook_security_group_filter"
        )
        p = self.load_policy(
            {
                "name": "sagemaker-notebook",
                "resource": "sagemaker-notebook",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "SGW-SG"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["NotebookInstanceName"], nb)

    def test_sagemaker_notebook_kms_alias(self):
        session_factory = self.replay_flight_data("test_sagemaker_notebook_kms_key_filter")
        kms = session_factory().client('kms')
        p = self.load_policy(
            {
                "name": "sagemaker-kms-alias",
                "resource": "aws.sagemaker-notebook",
                "filters": [
                    {
                        'NotebookInstanceName': "test-kms"
                    },
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "alias/skunk/trails",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['KmsKeyId'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/skunk/trails')


class TestModelInstance(BaseTest):

    def test_list_model(self):
        session_factory = self.replay_flight_data("test_sagemaker_model")
        p = self.load_policy(
            {"name": "list-sagemaker-model", "resource": "sagemaker-model"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)

    def test_filter_model(self):
        session_factory = self.replay_flight_data("test_sagemaker_model_filter")
        p = self.load_policy(
            {
                "name": "query-model",
                "resource": "sagemaker-model",
                "filters": [{"ExecutionRoleArn": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_model(self):
        session_factory = self.replay_flight_data("test_sagemaker_delete_model")
        p = self.load_policy(
            {
                "name": "delete-invalid-sagemaker-model",
                "resource": "sagemaker-model",
                "filters": [{"tag:DeleteMe": "present"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        try:
            client.describe_model(ModelName=resources[0]["ModelName"])
        except b_exc.ClientError as e:
            if e.response["Error"]["Code"] != "ValidationException":
                self.fail("Bad Error:" + e.response["Error"]["Code"])
            else:
                self.assertEqual(e.response["Error"]["Code"], "ValidationException")
        else:
            self.fail("Resource still exists")

    def test_tag_model(self):
        session_factory = self.replay_flight_data("test_sagemaker_tag_model")
        p = self.load_policy(
            {
                "name": "tag-sagemaker-model",
                "resource": "sagemaker-model",
                "filters": [{"tag:Category": "absent"}],
                "actions": [{"type": "tag", "key": "Category", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["ModelArn"])["Tags"]
        self.assertEqual(tags[0]["Value"], "TestValue")

    def test_remove_tag_model(self):
        session_factory = self.replay_flight_data("test_sagemaker_remove_tag_model")
        p = self.load_policy(
            {
                "name": "untag-sagemaker-model",
                "resource": "sagemaker-model",
                "filters": [{"tag:Category": "TestValue"}],
                "actions": [{"type": "remove-tag", "tags": ["Category"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["ModelArn"])["Tags"]
        self.assertEqual(len(tags), 0)

    def test_model_mark_for_op(self):
        session_factory = self.replay_flight_data("test_model_mark_for_op")
        p = self.load_policy(
            {
                "name": "mark-failed-model-delete",
                "resource": "sagemaker-model",
                "filters": [{"tag:OpMe": "present"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["ModelArn"])["Tags"]
        self.assertTrue(tags[0], "custodian_cleanup")

    def test_model_marked_for_op(self):
        session_factory = self.replay_flight_data("test_model_marked_for_op")
        p = self.load_policy(
            {
                "name": "marked-failed-endpoints-delete",
                "resource": "sagemaker-model",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "skew": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestSagemakerJob(BaseTest):

    def test_sagemaker_training_job_query(self):
        session_factory = self.replay_flight_data("test_sagemaker_training_job_query")
        p = self.load_policy(
            {
                "name": "query-training-jobs",
                "resource": "sagemaker-job",
                "query": [{"StatusEquals": "Failed"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_stop_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_training_job_stop")
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "stop-training-job",
                "resource": "sagemaker-job",
                "filters": [
                    {
                        "type": "value",
                        "key": "InputDataConfig[].ChannelName",
                        "value": "train",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job = client.describe_training_job(
            TrainingJobName=resources[0]["TrainingJobName"]
        )
        self.assertEqual(job["TrainingJobStatus"], "Stopping")

    def test_tag_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_training_job_tag")
        p = self.load_policy(
            {
                "name": "tag-training-job",
                "resource": "sagemaker-job",
                "filters": [{"tag:JobTag": "absent"}],
                "actions": [{"type": "tag", "key": "JobTag", "value": "JobTagValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["TrainingJobArn"])["Tags"]
        self.assertEqual([tags[0]["Key"], tags[0]["Value"]], ["JobTag", "JobTagValue"])

    def test_untag_job(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_training_job_remove_tag"
        )
        p = self.load_policy(
            {
                "name": "remove-training-job-tag",
                "resource": "sagemaker-job",
                "filters": [{"tag:JobTag": "JobTagValue"}],
                "actions": [{"type": "remove-tag", "tags": ["JobTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["TrainingJobArn"])["Tags"]
        self.assertEqual(len(tags), 0)


class TestSagemakerTransformJob(BaseTest):

    def test_sagemaker_transform_job_query(self):
        session_factory = self.replay_flight_data("test_sagemaker_transform_job_query")
        p = self.load_policy(
            {
                "name": "query-transform-jobs",
                "resource": "sagemaker-transform-job",
                "query": [{"StatusEquals": "Completed"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_stop_transform_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_transform_job_stop")
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "stop-transform-job",
                "resource": "sagemaker-transform-job",
                "filters": [
                    {
                        "type": "value",
                        "key": "ModelName",
                        "value": "kmeans",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job = client.describe_transform_job(
            TransformJobName=resources[0]["TransformJobName"]
        )
        self.assertEqual(job["TransformJobStatus"], "Stopping")

    def test_tag_transform_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_transform_job_tag")
        p = self.load_policy(
            {
                "name": "tag-transform-job",
                "resource": "sagemaker-transform-job",
                "filters": [{"tag:JobTag": "absent"}],
                "actions": [{"type": "tag", "key": "JobTag", "value": "JobTagValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["TransformJobArn"])["Tags"]
        self.assertEqual([tags[0]["Key"], tags[0]["Value"]], ["JobTag", "JobTagValue"])

    def test_untag_transform_job(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_transform_job_remove_tag"
        )
        p = self.load_policy(
            {
                "name": "remove-transform-job-tag",
                "resource": "sagemaker-transform-job",
                "filters": [{"tag:JobTag": "JobTagValue"}],
                "actions": [{"type": "remove-tag", "tags": ["JobTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["TransformJobArn"])["Tags"]
        self.assertEqual(len(tags), 0)


class TestSagemakerHyperParameterTuningJob(BaseTest):

    def test_sagemaker_hyperparameter_tuning_job_query(self):
        session_factory = self.replay_flight_data("test_sagemaker_hyperparameter_tuning_job_query")
        p = self.load_policy(
            {
                "name": "query-hyperparameter-tuning-jobs",
                "resource": "sagemaker-hyperparameter-tuning-job",
                "query": [{"StatusEquals": "Failed"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_stop_hyperparameter_tuning_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_hyperparameter_tuning_job_stop")
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "stop-hyperparameter-tuning-job",
                "resource": "sagemaker-hyperparameter-tuning-job",
                "filters": [
                    {
                        "type": "value",
                        "key": "HyperParameterTuningJobName",
                        "value": "test",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job = client.describe_hyper_parameter_tuning_job(
            HyperParameterTuningJobName=resources[0]["HyperParameterTuningJobName"]
        )
        self.assertEqual(job["HyperParameterTuningJobStatus"], "Stopping")

    def test_tag_hyperparameter_tuning_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_hyperparameter_tuning_job_tag")
        p = self.load_policy(
            {
                "name": "tag-hyperparameter-tuning-job",
                "resource": "sagemaker-hyperparameter-tuning-job",
                "filters": [{"tag:JobTag": "absent"}],
                "actions": [{"type": "tag", "key": "JobTag", "value": "JobTagValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["HyperParameterTuningJobArn"])["Tags"]
        self.assertEqual([tags[0]["Key"], tags[0]["Value"]], ["JobTag", "JobTagValue"])

        p = self.load_policy(
            {
                "name": "remove-hyperparameter-tuning-job-tag",
                "resource": "sagemaker-hyperparameter-tuning-job",
                "filters": [{"tag:JobTag": "JobTagValue"}],
                "actions": [{"type": "remove-tag", "tags": ["JobTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["HyperParameterTuningJobArn"])["Tags"]
        self.assertEqual(len(tags), 0)


class TestSageMakerAutoMLJob(BaseTest):

    def test_sagemaker_automl_job_query(self):
        session_factory = self.replay_flight_data("test_sagemaker_auto_ml_job_query")
        p = self.load_policy(
            {
                "name": "query-auto-ml-jobs",
                "resource": "sagemaker-auto-ml-job",
                "query": [{"StatusEquals": "Completed"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_stop_sagemaker_auto_ml_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_auto_ml_job_stop")
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "stop-auto-ml-job",
                "resource": "sagemaker-auto-ml-job",
                "filters": [
                    {
                        "type": "value",
                        "key": "AutoMLJobName",
                        "value": "Canvas",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job = client.describe_auto_ml_job_v2(AutoMLJobName=resources[0]["AutoMLJobName"])
        self.assertEqual(job["AutoMLJobStatus"], "Stopping")

    def test_tag_sagemaker_auto_ml_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_auto_ml_job_tag")
        p = self.load_policy(
            {
                "name": "tag-auto-ml-job",
                "resource": "sagemaker-auto-ml-job",
                "filters": [{"tag:JobTag": "absent"}],
                "actions": [{"type": "tag", "key": "JobTag", "value": "JobTagValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["AutoMLJobArn"])["Tags"]
        self.assertEqual([tags[0]["Key"], tags[0]["Value"]], ["JobTag", "JobTagValue"])

        p = self.load_policy(
            {
                "name": "remove-auto-ml-job-tag",
                "resource": "sagemaker-auto-ml-job",
                "filters": [{"tag:JobTag": "JobTagValue"}],
                "actions": [{"type": "remove-tag", "tags": ["JobTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["AutoMLJobArn"])["Tags"]
        assert "JobTag" not in [tag["Key"] for tag in tags]


class TestSagemakerCompilationJob(BaseTest):

    def test_sagemaker_compilation_job_query(self):
        session_factory = self.replay_flight_data("test_sagemaker_compilation_job_query")
        p = self.load_policy(
            {
                "name": "query-compilation-jobs",
                "resource": "sagemaker-compilation-job",
                "query": [{"StatusEquals": "FAILED"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_tag_sagemaker_compilation_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_compilation_job_tag")
        p = self.load_policy(
            {
                "name": "tag-compilation-job",
                "resource": "sagemaker-compilation-job",
                "filters": [{"tag:JobTag": "absent"}],
                "actions": [{"type": "tag", "key": "JobTag", "value": "JobTagValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["CompilationJobArn"])["Tags"]
        self.assertEqual([tags[0]["Key"], tags[0]["Value"]], ["JobTag", "JobTagValue"])

        p = self.load_policy(
            {
                "name": "remove-compilation-job-tag",
                "resource": "sagemaker-compilation-job",
                "filters": [{"tag:JobTag": "JobTagValue"}],
                "actions": [{"type": "remove-tag", "tags": ["JobTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["CompilationJobArn"])["Tags"]
        assert "JobTag" not in [tag["Key"] for tag in tags]

    def test_stop_sagemaker_compilation_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_compilation_job_stop")
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "stop-compilation-job",
                "resource": "sagemaker-compilation-job",
                "filters": [
                    {
                        "type": "value",
                        "key": "CompilationJobName",
                        "value": "c7n",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job = client.describe_compilation_job(
            CompilationJobName=resources[0]["CompilationJobName"]
        )
        self.assertEqual(job["CompilationJobStatus"], "STOPPING")


class TestSageMakerModelBiasJobDefinition(BaseTest):

    def test_sagemaker_model_bias_job_query(self):
        session_factory = self.replay_flight_data("test_sagemaker_model_bias_job_definition_query")
        p = self.load_policy(
            {
                "name": "query-model-bias-job-definition",
                "resource": "sagemaker-model-bias-job-definition",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_sagemaker_model_bias_job_definition(self):
        session_factory = self.replay_flight_data("test_sagemaker_model_bias_job_definition_delete")
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "delete-model-bias-job-definition",
                "resource": "sagemaker-model-bias-job-definition",
                "filters": [
                    {
                        "type": "value",
                        "key": "MonitoringJobDefinitionName",
                        "value": "test",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        jobs = client.list_model_bias_job_definitions().get("JobDefinitionSummaries")
        self.assertEqual(len(jobs), 0)

    def test_tag_data_sagemaker_model_bias_job_definition(self):
        session_factory = self.replay_flight_data("test_sagemaker_model_bias_job_definition_tag")
        p = self.load_policy(
            {
                "name": "tag-model-bias-job-definition",
                "resource": "sagemaker-model-bias-job-definition",
                "filters": [{"tag:Owner": "absent"}],
                "actions": [{"type": "tag", "key": "Owner", "value": "c7n"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["JobDefinitionArn"])["Tags"]
        self.assertEqual(tags[1]['Key'], 'Owner')
        self.assertEqual(tags[1]['Value'], 'c7n')

        p = self.load_policy(
            {
                "name": "remove-model-bias-job-definition-tag",
                "resource": "sagemaker-model-bias-job-definition",
                "filters": [{"tag:Owner": "c7n"}],
                "actions": [{"type": "remove-tag", "tags": ["Owner"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["JobDefinitionArn"])["Tags"]
        self.assertEqual(len(tags), 1)


class TestSagemakerProcessingJob(BaseTest):

    def test_sagemaker_processing_job_query(self):
        session_factory = self.replay_flight_data("test_sagemaker_processing_job_query")
        p = self.load_policy(
            {
                "name": "query-processing-jobs",
                "resource": "sagemaker-processing-job",
                "query": [{"StatusEquals": "Failed"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_tag_sagemaker_processing_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_processing_job_tag")
        p = self.load_policy(
            {
                "name": "tag-processing-job",
                "resource": "sagemaker-processing-job",
                "filters": [{"tag:JobTag": "absent"}],
                "actions": [{"type": "tag", "key": "JobTag", "value": "JobTagValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["ProcessingJobArn"])["Tags"]
        self.assertEqual([tags[0]["Key"], tags[0]["Value"]], ["JobTag", "JobTagValue"])

        p = self.load_policy(
            {
                "name": "remove-processing-job-tag",
                "resource": "sagemaker-processing-job",
                "filters": [{"tag:JobTag": "JobTagValue"}],
                "actions": [{"type": "remove-tag", "tags": ["JobTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["ProcessingJobArn"])["Tags"]
        assert "JobTag" not in [tag["Key"] for tag in tags]

    def test_stop_sagemaker_processing_job(self):
        session_factory = self.replay_flight_data("test_sagemaker_processing_job_stop")
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "stop-processing-job",
                "resource": "sagemaker-processing-job",
                "filters": [
                    {
                        "type": "value",
                        "key": "ProcessingJobName",
                        "value": "c7n",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job = client.describe_processing_job(
            ProcessingJobName=resources[0]["ProcessingJobName"]
        )
        self.assertEqual(job["ProcessingJobStatus"], "Stopping")


class TestSagemakerEndpoint(BaseTest):

    def test_sagemaker_endpoints(self):
        session_factory = self.replay_flight_data("test_sagemaker_endpoints")
        p = self.load_policy(
            {"name": "list-endpoints", "resource": "sagemaker-endpoint"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_sagemaker_endpoint_delete(self):
        session_factory = self.replay_flight_data("test_sagemaker_endpoint_delete")
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "delete-endpoint-by-config",
                "resource": "sagemaker-endpoint",
                "filters": [{"EndpointConfigName": "kmeans-2018-01-18-19-25-36-887"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        status = client.describe_endpoint(EndpointName=resources[0]["EndpointName"])[
            "EndpointStatus"
        ]
        self.assertEqual(status, "Deleting")

    def test_sagemaker_endpoint_tag(self):
        session_factory = self.replay_flight_data("test_sagemaker_endpoint_tag")
        p = self.load_policy(
            {
                "name": "endpoint-tag-missing",
                "resource": "sagemaker-endpoint",
                "filters": [{"tag:required-tag": "absent"}],
                "actions": [
                    {"type": "tag", "key": "required-tag", "value": "required-value"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["EndpointArn"])["Tags"]
        self.assertTrue(tags[0]["Key"], "required-tag")
        self.assertTrue(tags[0]["Key"], "required-value")

    def test_sagemaker_endpoint_remove_tag(self):
        session_factory = self.replay_flight_data("test_sagemaker_endpoint_remove_tag")
        p = self.load_policy(
            {
                "name": "endpoint-required-tag-obsolete",
                "resource": "sagemaker-endpoint",
                "filters": [{"tag:expired-tag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["expired-tag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["EndpointArn"])["Tags"]
        self.assertEqual(len(tags), 0)

    def test_sagemaker_endpoint_mark_for_op(self):
        session_factory = self.replay_flight_data("test_sagemaker_endpoint_mark_for_op")
        p = self.load_policy(
            {
                "name": "mark-failed-endpoints-delete",
                "resource": "sagemaker-endpoint",
                "filters": [{"EndpointStatus": "Failed"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["EndpointArn"])["Tags"]
        self.assertTrue(tags[0], "custodian_cleanup")

    def test_sagemaker_endpoint_marked_for_op(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_endpoint_marked_for_op"
        )
        p = self.load_policy(
            {
                "name": "marked-failed-endpoints-delete",
                "resource": "sagemaker-endpoint",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "skew": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestSagemakerEndpointConfig(BaseTest):

    def test_sagemaker_endpoint_config(self):
        session_factory = self.replay_flight_data("test_sagemaker_endpoint_config")
        p = self.load_policy(
            {"name": "list-endpoint-configs", "resource": "sagemaker-endpoint-config"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_sagemaker_endpoint_config_delete(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_endpoint_config_delete"
        )
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "delete-endpoint-config",
                "resource": "sagemaker-endpoint-config",
                "filters": [
                    {
                        "type": "value",
                        "key": "ProductionVariants[].InstanceType",
                        "value": "ml.m4.xlarge",
                        "op": "contains",
                    }
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        configs = client.list_endpoint_configs()["EndpointConfigs"]
        self.assertEqual(len(configs), 0)

    def test_sagemaker_endpoint_config_tag(self):
        session_factory = self.replay_flight_data("test_sagemaker_endpoint_config_tag")
        p = self.load_policy(
            {
                "name": "endpoint-config-tag-missing",
                "resource": "sagemaker-endpoint-config",
                "filters": [{"tag:required-tag": "absent"}],
                "actions": [
                    {"type": "tag", "key": "required-tag", "value": "required-value"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["EndpointConfigArn"])["Tags"]
        self.assertEqual(
            [tags[0]["Key"], tags[0]["Value"]], ["required-tag", "required-value"]
        )

    def test_sagemaker_endpoint_config_remove_tag(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_endpoint_config_remove_tag"
        )
        p = self.load_policy(
            {
                "name": "endpoint-config-required-tag-obsolete",
                "resource": "sagemaker-endpoint-config",
                "filters": [{"tag:expired-tag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["expired-tag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["EndpointConfigArn"])["Tags"]
        self.assertEqual(len(tags), 0)

    def test_sagemaker_endpoint_config_mark_for_op(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_endpoint_config_mark_for_op"
        )
        p = self.load_policy(
            {
                "name": "mark-endpoint-config-mark-for-op-delete",
                "resource": "sagemaker-endpoint-config",
                "filters": [
                    {
                        "type": "value",
                        "key": "ProductionVariants[].InstanceType",
                        "value": "ml.m4.xlarge",
                        "op": "contains",
                    }
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["EndpointConfigArn"])["Tags"]
        self.assertTrue(tags[0], "custodian_cleanup")

    def test_sagemaker_endpoint_config_marked_for_op(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_endpoint_config_marked_for_op"
        )
        p = self.load_policy(
            {
                "name": "marked-failed-endpoint-config-delete",
                "resource": "sagemaker-endpoint-config",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "skew": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_sagemaker_endpoint_config_kms_alias(self):
        session_factory = self.replay_flight_data("test_sagemaker_endpoint_config_kms_key_filter")
        kms = session_factory().client('kms')
        p = self.load_policy(
            {
                "name": "sagemaker-kms-alias",
                "resource": "aws.sagemaker-endpoint-config",
                "filters": [
                    {
                        "EndpointConfigName": "kms-test"
                    },
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "alias/skunk/trails",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['KmsKeyId'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/skunk/trails')


class TestSagemakerDomain(BaseTest):

    def test_tag_sagemaker_domain(self):
        session_factory = self.replay_flight_data("test_tag_sagemaker_domain")
        p = self.load_policy(
            {
                "name": "tag-sagemaker-domain",
                "resource": "sagemaker-domain",
                "filters": [{"tag:owner": "absent"}],
                "actions": [{"type": "tag", "key": "owner", "value": "policy"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["DomainArn"])["Tags"]
        self.assertEqual(tags[0]['Key'], 'owner')
        self.assertEqual(tags[0]['Value'], 'policy')

        p = self.load_policy(
            {
                "name": "untag-sagemaker-domain",
                "resource": "sagemaker-domain",
                "filters": [{"tag:owner": "policy"}],
                "actions": [{"type": "remove-tag", "tags": ["owner"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["DomainArn"])["Tags"]
        self.assertEqual(len(tags), 0)

    def test_sagemaker_domain_kms_alias(self):
        session_factory = self.replay_flight_data("test_sagemaker_domain_kms_key_filter")
        kms = session_factory().client('kms')
        p = self.load_policy(
            {
                "name": "sagemaker-domain-kms-alias",
                "resource": "aws.sagemaker-domain",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "alias/sagemaker",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['KmsKeyId'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/sagemaker')


class TestCluster(BaseTest):

    def test_tag_cluster(self):
        session_factory = self.replay_flight_data("test_sagemaker_tag_cluster")
        p = self.load_policy(
            {
                "name": "tag-sagemaker-cluster",
                "resource": "sagemaker-cluster",
                "filters": [{"tag:Owner": "absent"}],
                "actions": [{"type": "tag", "key": "Owner", "value": "c7n"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["ClusterArn"])["Tags"]
        self.assertEqual(tags[0]['Key'], 'Owner')
        self.assertEqual(tags[0]['Value'], 'c7n')

        p = self.load_policy(
            {
                "name": "untag-sagemaker-cluster",
                "resource": "sagemaker-cluster",
                "filters": [{"tag:Owner": "c7n"}],
                "actions": [{"type": "remove-tag", "tags": ["Owner"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["ClusterArn"])["Tags"]
        self.assertEqual(len(tags), 0)

    def test_delete_cluster(self):
        session_factory = self.replay_flight_data("test_sagemaker_delete_cluster")
        p = self.load_policy(
            {
                "name": "delete-sagemaker-cluster",
                "resource": "sagemaker-cluster",
                "filters": [{"ClusterName": "test-c7n-cluster"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("sagemaker")
        notebook = client.describe_cluster(
            ClusterName=resources[0]["ClusterName"]
        )
        self.assertTrue(notebook["ClusterStatus"], "Deleting")

    def test_cluster_subnet(self):
        c = "c7n-test-cluster"
        session_factory = self.replay_flight_data("test_sagemaker_cluster_subnet_filter")
        p = self.load_policy(
            {
                "name": "sagemaker-cluster",
                "resource": "sagemaker-cluster",
                "filters": [{"type": "subnet", "key": "tag:Name", "value": "PrivateSubnetA"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ClusterName"], c)

    def test_cluster_security_group(self):
        c = "c7n-test-cluster"
        session_factory = self.replay_flight_data(
            "test_sagemaker_cluster_security_group_filter"
        )
        p = self.load_policy(
            {
                "name": "sagemaker-cluster",
                "resource": "sagemaker-cluster",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ClusterName"], c)


class TestDataQualityJobDefinition(BaseTest):

    def test_sagemaker_data_quality_job_definition_delete(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_data_quality_job_definition_delete"
        )
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "delete-data-quality-job-definition",
                "resource": "sagemaker-data-quality-job-definition",
                "filters": [{"JobDefinitionName": "c7n-test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job_defs = client.list_data_quality_job_definitions().get("JobDefinitionSummaries")
        self.assertEqual(job_defs, [])

    def test_tag_data_quality_job_definition(self):
        session_factory = self.replay_flight_data("test_sagemaker_data_quality_job_definition_tag")
        p = self.load_policy(
            {
                "name": "tag-data-quality-job-definition",
                "resource": "sagemaker-data-quality-job-definition",
                "filters": [{"tag:Owner": "absent"}],
                "actions": [{"type": "tag", "key": "Owner", "value": "c7n"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["JobDefinitionArn"])["Tags"]
        self.assertEqual(tags[0]['Key'], 'Owner')
        self.assertEqual(tags[0]['Value'], 'c7n')

        p = self.load_policy(
            {
                "name": "remove-data-quality-job-definition-tag",
                "resource": "sagemaker-data-quality-job-definition",
                "filters": [{"tag:Owner": "c7n"}],
                "actions": [{"type": "remove-tag", "tags": ["Owner"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["JobDefinitionArn"])["Tags"]
        self.assertEqual(len(tags), 0)


class TestModelExplainabilityJobDefinition(BaseTest):

    def test_sagemaker_model_explainability_job_definition_delete(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_model_explainability_job_definition_delete"
        )
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "delete-model-explainability-job-definition",
                "resource": "sagemaker-model-explainability-job-definition",
                "filters": [{"JobDefinitionName": "c7n-test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job_defs = client.list_model_explainability_job_definitions().get("JobDefinitionSummaries")
        self.assertEqual(job_defs, [])

    def test_tag_model_explainability_job_definition(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_model_explainability_job_definition_tag"
        )
        p = self.load_policy(
            {
                "name": "tag-model-explainability-job-definition",
                "resource": "sagemaker-model-explainability-job-definition",
                "filters": [{"tag:Owner": "absent"}],
                "actions": [{"type": "tag", "key": "Owner", "value": "c7n"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["JobDefinitionArn"])["Tags"]
        self.assertEqual(tags[0]['Key'], 'Owner')
        self.assertEqual(tags[0]['Value'], 'c7n')

        p = self.load_policy(
            {
                "name": "remove-model-explainability-job-definition-tag",
                "resource": "sagemaker-model-explainability-job-definition",
                "filters": [{"tag:Owner": "c7n"}],
                "actions": [{"type": "remove-tag", "tags": ["Owner"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["JobDefinitionArn"])["Tags"]
        self.assertEqual(len(tags), 0)


class TestModelQualityJobDefinition(BaseTest):

    def test_sagemaker_model_quality_job_definition_delete(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_model_quality_job_definition_delete"
        )
        client = session_factory(region="us-east-1").client("sagemaker")
        p = self.load_policy(
            {
                "name": "delete-model-quality-job-definition",
                "resource": "sagemaker-model-quality-job-definition",
                "filters": [{"JobDefinitionName": "c7n-test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        job_defs = client.list_model_quality_job_definitions().get("JobDefinitionSummaries")
        self.assertEqual(job_defs, [])

    def test_tag_model_quality_job_definition(self):
        session_factory = self.replay_flight_data(
            "test_sagemaker_model_quality_job_definition_tag"
        )
        p = self.load_policy(
            {
                "name": "tag-model-quality-job-definition",
                "resource": "sagemaker-model-quality-job-definition",
                "filters": [{"tag:Owner": "absent"}],
                "actions": [{"type": "tag", "key": "Owner", "value": "c7n"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("sagemaker")
        tags = client.list_tags(ResourceArn=resources[0]["JobDefinitionArn"])["Tags"]
        self.assertEqual(tags[0]['Key'], 'Owner')
        self.assertEqual(tags[0]['Value'], 'c7n')

        p = self.load_policy(
            {
                "name": "remove-model-quality-job-definition-tag",
                "resource": "sagemaker-model-quality-job-definition",
                "filters": [{"tag:Owner": "c7n"}],
                "actions": [{"type": "remove-tag", "tags": ["Owner"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags(ResourceArn=resources[0]["JobDefinitionArn"])["Tags"]
        self.assertEqual(len(tags), 0)


class SagemakerJobQueryParse(BaseTest):

    def test_query(self):
        query = [
            {'StatusEquals': 'InProgress'},
            {'NameContains': 'c7n'},
            {'CreationTimeAfter': 1470968567.05},
            {'LastModifiedTimeBefore': '2022-09-15T17:15:20.000Z'},
            {'MaxResults': 1000},
        ]
        self.assertEqual(query, SagemakerJobQueryParser.parse(query))

    def test_invalid_query(self):
        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, {})

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [None])

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [{'X': 1}])

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [
                {'Name': 'StatusEquals', 'Values': ['InProgress']}])

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [
                {'StatusEquals': 'INPROGRESS'}])

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [
                {'StatusEquals': ['InProgress']}])

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [
                {'CreationTimeAfter': 1}])

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [
                {'MaxResults': '10'}])


class CompilationJobQueryParse(BaseTest):

    def test_query(self):
        query = [{'StatusEquals': 'FAILED'}, {'NameContains': 'test'}]
        self.assertEqual(query, CompilationJobQueryParser.parse(query))

    def test_invalid_query(self):

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [
                {'StatusEquals', 'InProgress'}])

        self.assertRaises(
            PolicyValidationError, SagemakerJobQueryParser.parse, [
                {'StatusEquals': ['INPROGRESS', 'COMPLETED']}])


@pytest.mark.audited
@terraform('sagemaker_studio', scope='module')
def test_sagemaker_user_profile(test, sagemaker_studio):
    # tests the sagemaker-user-profile-untagged example policy: verify the
    # tagged profile is excluded and the untagged profile is included.
    factory = test.replay_flight_data('test_sagemaker_user_profile')
    p = test.load_policy(
        {
            'name': 'sagemaker-user-profile-untagged',
            'resource': 'sagemaker-user-profile',
            'filters': [{'tag:favorite-color': 'absent'}],
        },
        session_factory=factory,
    )
    [resource] = p.run()
    assert resource['UserProfileName'] == sagemaker_studio[
        'aws_sagemaker_user_profile.untagged.user_profile_name']


@pytest.mark.audited
@terraform('sagemaker_studio', scope='module')
def test_sagemaker_space(test, sagemaker_studio):
    # tests the sagemaker-space-untagged example policy: verify the tagged
    # space is excluded and the untagged space is included.
    factory = test.replay_flight_data('test_sagemaker_space')
    p = test.load_policy(
        {
            'name': 'sagemaker-space-untagged',
            'resource': 'sagemaker-space',
            'filters': [{'tag:favorite-color': 'absent'}],
        },
        session_factory=factory,
    )
    [resource] = p.run()
    assert resource['SpaceName'] == sagemaker_studio[
        'aws_sagemaker_space.untagged.space_name']


@pytest.mark.audited
@terraform('sagemaker_studio', scope='module')
def test_sagemaker_app(test, sagemaker_studio):
    # tests the sagemaker-app-untagged example policy: verify the tagged app
    # is excluded and the untagged app is included.
    #
    # SageMaker retains app metadata (and keeps returning it from ListApps
    # with Status Deleted/Deleting) for up to 24 hours after an app is shut
    # down, so apps from earlier test recordings against now-destroyed
    # domains can otherwise still show up here too. See the CreationTime
    # note on:
    # https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_DescribeApp.html
    factory = test.replay_flight_data('test_sagemaker_app')
    p = test.load_policy(
        {
            'name': 'sagemaker-app-untagged',
            'resource': 'sagemaker-app',
            'filters': [
                {'type': 'value', 'key': 'Status', 'op': 'not-in',
                 'value': ['Deleted', 'Deleting']},
                {'tag:favorite-color': 'absent'},
            ],
        },
        session_factory=factory,
    )
    [resource] = p.run()
    assert resource['AppName'] == sagemaker_studio['aws_sagemaker_app.untagged.app_name']


def capture_dimensions():
    """Capture the dimensions of each GetMetricStatistics call.

    Flight data is matched on the api call name alone, so asserting on the
    resources a policy returns says nothing about the dimensions it asked
    cloudwatch for -- which is the whole of what these filters do.
    """
    dimensions = []
    get_metric_data = MetricsFilter.get_metric_data

    def record(self, client, params):
        dimensions.append(params['Dimensions'])
        return get_metric_data(self, client, params)

    return dimensions, mock.patch.object(
        MetricsFilter, 'get_metric_data', record)

################################################################################
#
# Tests that test that we actually fetch correct data by running
# policies that depend on it.
# Two policies, each run against both kinds of endpoint:
#
#   test                             policy                  endpoints
#   -------------------------------  ----------------------  -------------------
#   idle                             Invocations Sum lte 0   two classic
#   inference_component              the same policy         component
#   idle_component                   the same policy         component, uncalled
#   utilization                      CPUUtilization Average  classic
#                                    less-than 400
#   inference_component_utilization  the same policy         component
#
# idle_component is why the idle policy needs no missing-value: an endpoint
# nothing has called reports a zero for each interval rather than nothing
# at all, whichever way it hosts its models. What a missing value is for --
# a metric with no values to compare -- is covered by the two unit tests
# below it, which don't need an endpoint.
#
# The catalogue tests further down cover which metrics can be asked for and
# whether their dimension sets carry data. These cover what a policy
# decides once it has the data.
#


@pytest.mark.audited
@terraform('sagemaker_endpoint_metrics', scope='module')
def test_sagemaker_endpoint_metrics_idle(test, sagemaker_endpoint_metrics):
    # the busy endpoint's invocations land on its second variant, so it is
    # only distinguishable from the idle endpoint if every variant is queried
    busy = sagemaker_endpoint_metrics['aws_sagemaker_endpoint.busy.name']
    idle = sagemaker_endpoint_metrics['aws_sagemaker_endpoint.idle.name']
    factory = test.replay_flight_data(
        'test_sagemaker_endpoint_metrics_idle')

    if test.recording:
        runtime = factory().client('sagemaker-runtime')
        for _ in range(5):
            runtime.invoke_endpoint(
                EndpointName=busy,
                TargetVariant='busy',
                ContentType='text/csv',
                Body='1.0',
                )
        time.sleep(300)

    p = test.load_policy(
        {
            'name': 'sagemaker-endpoints-idle',
            'resource': 'sagemaker-endpoint',
            'filters': [
                {'type': 'value', 'key': 'EndpointName',
                 'op': 'in', 'value': [busy, idle]},
                {'type': 'metrics',
                 'name': 'Invocations',
                 'statistics': 'Sum',
                 'days': 1,
                 'period': 86400,
                 'value': 0,
                 'op': 'lte'},
            ],
        },
        session_factory=factory,
    )
    dimensions, capture = capture_dimensions()
    with capture:
        [resource] = p.run()
    assert resource['EndpointName'] == idle
    # the gpu variant is never queried: busy's second variant already
    # fails the condition, which settles the endpoint
    assert [[d['Value'] for d in dims] for dims in dimensions] == [
        [busy, 'quiet'], [busy, 'busy'], [idle, 'AllTraffic']]
    assert [d['Name'] for d in dimensions[0]] == ['EndpointName', 'VariantName']


@pytest.mark.audited
@terraform('sagemaker_endpoint_metrics', scope='module')
def test_sagemaker_endpoint_metrics_utilization(test, sagemaker_endpoint_metrics):
    # instance utilization metrics are in a namespace of their own, and are
    # reported by every variant whether or not it is being invoked
    busy = sagemaker_endpoint_metrics['aws_sagemaker_endpoint.busy.name']
    factory = test.replay_flight_data(
        'test_sagemaker_endpoint_metrics_utilization')

    p = test.load_policy(
        {
            'name': 'sagemaker-endpoints-underused',
            'resource': 'sagemaker-endpoint',
            'filters': [
                {'EndpointName': busy},
                {'type': 'metrics',
                 'name': 'CPUUtilization',
                 'statistics': 'Average',
                 'days': 1,
                 'period': 3600,
                 'value': 400,
                 'op': 'less-than'},
            ],
        },
        session_factory=factory,
    )
    dimensions, capture = capture_dimensions()
    with capture:
        [resource] = p.run()
    assert resource['EndpointName'] == busy
    assert [[d['Value'] for d in dims] for dims in dimensions] == [
        [busy, 'quiet'], [busy, 'busy'], [busy, 'gpu']]
    # each variant's series is annotated separately, named by its dimensions
    annotated = resource['c7n.metrics']
    assert sorted(key.split('.')[-1] for key in annotated) == [
        'VariantName=busy', 'VariantName=gpu', 'VariantName=quiet']
    assert [len(points) for points in annotated.values()] == [1, 1, 1]


@pytest.mark.audited
@terraform('sagemaker_endpoint_metrics', scope='module')
def test_sagemaker_endpoint_metrics_inference_component(
        test, sagemaker_endpoint_metrics):
    # this endpoint's variant hosts no model -- the model arrives as an
    # inference component, and its invocations are published under the
    # component's name with no EndpointName dimension anywhere. Querying
    # the variant returns nothing, which an idle policy would read as idle.
    endpoint = sagemaker_endpoint_metrics.outputs[
        'component_endpoint_name']['value']
    component = sagemaker_endpoint_metrics.outputs['component_name']['value']
    factory = test.replay_flight_data(
        'test_sagemaker_endpoint_metrics_inference_component')

    if test.recording:
        runtime = factory().client('sagemaker-runtime')
        for _ in range(5):
            runtime.invoke_endpoint(
                EndpointName=endpoint,
                InferenceComponentName=component,
                ContentType='text/csv',
                Body='1.0',
                )
        time.sleep(300)

    p = test.load_policy(
        {
            'name': 'sagemaker-endpoints-idle',
            'resource': 'sagemaker-endpoint',
            'filters': [
                {'EndpointName': endpoint},
                {'type': 'metrics',
                 'name': 'Invocations',
                 'statistics': 'Sum',
                 'days': 1,
                 'period': 86400,
                 'value': 0,
                 'op': 'lte'},
            ],
        },
        session_factory=factory,
    )
    dimensions, capture = capture_dimensions()
    with capture:
        resources = p.run()

    # the endpoint is serving traffic, so an idle policy must skip it
    assert resources == []
    # and it must have asked about the component, not the variant
    assert [[(d['Name'], d['Value']) for d in dims] for dims in dimensions] == [
        [('InferenceComponentName', component)]]


@pytest.mark.audited
@terraform('sagemaker_endpoint_metrics', scope='module')
def test_sagemaker_endpoint_metrics_idle_component(
        test, sagemaker_endpoint_metrics):
    # a component endpoint nobody has called still publishes a zero for
    # each interval, the same as a classic one, so an idle policy finds it
    # from its own values and doesn't need a missing value to do it.
    endpoint = sagemaker_endpoint_metrics.outputs[
        'idle_component_endpoint_name']['value']
    factory = test.replay_flight_data(
        'test_sagemaker_endpoint_metrics_idle_component')

    idle = {
        'name': 'sagemaker-endpoints-idle',
        'resource': 'sagemaker-endpoint',
        'filters': [
            {'EndpointName': endpoint},
            {'type': 'metrics',
             'name': 'Invocations',
             'statistics': 'Sum',
             'days': 1,
             'period': 86400,
             'value': 0,
             'op': 'lte'},
            ],
        }
    p = test.load_policy(idle, session_factory=factory)
    [resource] = p.run()
    assert resource['EndpointName'] == endpoint
    # a published zero, not an absence of data
    [points] = resource['c7n.metrics'].values()
    assert [point['Sum'] for point in points] == [0.0]

    # so a missing value would make no difference to it
    idle['filters'][1]['missing-value'] = 0
    p = test.load_policy(idle, session_factory=factory)
    [resource] = p.run()
    assert resource['EndpointName'] == endpoint


@pytest.mark.audited
@terraform('sagemaker_endpoint_metrics', scope='module')
def test_sagemaker_endpoint_metrics_inference_component_utilization(
        test, sagemaker_endpoint_metrics):
    # utilization stays with the variant on a component-hosting endpoint,
    # even though its invocations moved to the component -- the namespace
    # decides the sub unit, not the endpoint
    endpoint = sagemaker_endpoint_metrics.outputs[
        'component_endpoint_name']['value']
    factory = test.replay_flight_data(
        'test_sagemaker_endpoint_metrics_inference_component_utilization')

    p = test.load_policy(
        {
            'name': 'sagemaker-endpoints-underused',
            'resource': 'sagemaker-endpoint',
            'filters': [
                {'EndpointName': endpoint},
                {'type': 'metrics',
                 'name': 'CPUUtilization',
                 'statistics': 'Average',
                 'days': 1,
                 'period': 3600,
                 'value': 400,
                 'op': 'less-than'},
            ],
        },
        session_factory=factory,
    )
    dimensions, capture = capture_dimensions()
    with capture:
        [resource] = p.run()

    assert resource['EndpointName'] == endpoint
    assert [[d['Name'] for d in dims] for dims in dimensions] == [
        ['EndpointName', 'VariantName']]

#
################################################################################


def test_sagemaker_endpoint_metrics_dimensions_validated(test):
    # a dimension aws never publishes this metric under is a policy error,
    # rather than a query that quietly returns nothing
    policy = {
        'name': 'sagemaker-endpoints-idle',
        'resource': 'sagemaker-endpoint',
        'filters': [
            {'type': 'metrics',
             'name': 'Invocations',
             'value': 0,
             'dimensions': {'QueueName': 'nope'}},
        ],
    }
    with pytest.raises(PolicyValidationError) as caught:
        test.load_policy(policy, validate=True)
    assert "can't use dimensions ['QueueName']" in str(caught.value)

    # the documentation lists instance type, but the only sets carrying it
    # also carry AvailabilityZone and Region, which no policy can supply,
    # so it isn't in the catalogue and naming it is an error too
    policy['filters'][0]['dimensions'] = {'InstanceType': 'ml.m5.large'}
    with pytest.raises(PolicyValidationError) as caught:
        test.load_policy(policy, validate=True)
    assert "can't use dimensions ['InstanceType']" in str(caught.value)

    # the namespace follows from the metric name, so naming it is an error
    del policy['filters'][0]['dimensions']
    policy['filters'][0]['namespace'] = '/aws/sagemaker/Endpoints'
    with pytest.raises(PolicyValidationError) as caught:
        test.load_policy(policy, validate=True)
    assert 'determines the namespace' in str(caught.value)

    # and keys of the shared schema this filter doesn't implement are
    # refused rather than ignored
    del policy['filters'][0]['namespace']
    policy['filters'][0]['percent-attr'] = 'InstanceCount'
    with pytest.raises(PolicyValidationError) as caught:
        test.load_policy(policy, validate=True)
    assert "doesn't support percent-attr" in str(caught.value)

    # a metric the documentation doesn't describe fails while the policy
    # is loading, rather than as an empty report later
    del policy['filters'][0]['percent-attr']
    policy['filters'][0]['name'] = 'Invocation'
    with pytest.raises(AssertionError) as caught:
        test.load_policy(policy, validate=True)
    assert 'no documented sagemaker-endpoint metric named Invocation' in str(
        caught.value)


def test_sagemaker_metrics_missing_value(test):
    # A metric with no values over the window leaves nothing to compare the
    # condition against. The missing value stands in for them, and without
    # one the endpoint is passed over rather than guessed about.
    from c7n.resources.sagemaker import SageMakerMetricsFilter

    def no_data(self, client, params):
        return []

    test.patch(SageMakerMetricsFilter, 'get_metric_data', no_data)
    policy = test.load_policy(
        {'name': 'endpoints', 'resource': 'sagemaker-endpoint'})
    metrics_filter = SagemakerEndpoint.filter_registry.get('metrics')

    def selected(**extra):
        """Does an idle-endpoint policy select an endpoint?"""
        # a fresh endpoint each time: the annotation is also the cache, so
        # one that has been through the filter isn't queried again
        endpoint = {'EndpointName': 'e',
                    'ProductionVariants': [{'VariantName': 'AllTraffic'}]}
        f = metrics_filter(
            dict(type='metrics', name='Invocations', statistics='Sum',
                 value=0, op='lte', **extra),
            policy.resource_manager)
        f.endpoint_components = {}  # a classic endpoint
        return f.process([endpoint]) == [endpoint]

    assert selected(**{'missing-value': 0})
    assert not selected()

    def reports_invocations(self, client, params):
        return [{'Sum': 5}]

    test.patch(SageMakerMetricsFilter, 'get_metric_data', reports_invocations)
    assert not selected()
    assert not selected(**{'missing-value': 0})

    def zero(self, client, params):
        return [{'Sum': 0}]

    test.patch(SageMakerMetricsFilter, 'get_metric_data', zero)
    assert selected()
    assert selected(**{'missing-value': 0})


def test_sagemaker_metrics_percentile_statistics(test):
    # a percentile is requested as ExtendedStatistics and comes back nested
    # under that key, rather than beside Timestamp like a standard statistic
    from c7n.resources.sagemaker import SageMakerMetricsFilter

    class OneSubUnit(SageMakerMetricsFilter):

        def get_dimensions_set(self, resource):
            return [{'D': 'only'}]

    requested = []

    def get_metric_data(self, client, params):
        requested.append(params)
        return [{'Timestamp': 'when', 'Unit': 'Percent',
                 'ExtendedStatistics': {'p95': 3.1}}]

    test.patch(SageMakerMetricsFilter, 'get_metric_data', get_metric_data)
    policy = test.load_policy(
        {'name': 'endpoints', 'resource': 'sagemaker-endpoint'})
    f = OneSubUnit(
        {'type': 'metrics', 'name': 'CPUUtilization', 'statistics': 'p95',
         'value': 50, 'op': 'less-than'}, policy.resource_manager)
    resource = {'EndpointName': 'e'}

    assert f.process([resource]) == [resource]
    # asked for the percentile as an extended statistic
    assert requested[0]['ExtendedStatistics'] == ['p95']
    assert 'Statistics' not in requested[0]
    # and the annotation holds the unwrapped values, not the nesting
    [points] = resource['c7n.metrics'].values()
    assert points == [{'p95': 3.1}]


def test_sagemaker_metrics_stop_fetching_once_a_value_fails(test):
    # a resource with several sub units costs a call each, and one failing
    # value settles it, so the rest are never fetched
    from c7n.resources.sagemaker import SageMakerMetricsFilter

    class ThreeSubUnits(SageMakerMetricsFilter):

        def get_dimensions_set(self, resource):
            return [{'D': str(i)} for i in range(3)]

    requested = []

    def get_metric_data(self, client, params):
        value = params['Dimensions'][0]['Value']
        requested.append(value)
        # the first sub unit fails the condition, the others would pass
        return [{'Average': 100 if value == '0' else 1}]

    test.patch(SageMakerMetricsFilter, 'get_metric_data', get_metric_data)
    policy = test.load_policy(
        {'name': 'endpoints', 'resource': 'sagemaker-endpoint'})
    f = ThreeSubUnits(
        {'type': 'metrics', 'name': 'CPUUtilization', 'value': 50,
         'op': 'less-than'}, policy.resource_manager)
    assert f.process([{'EndpointName': 'e'}]) == []
    assert requested == ['0']


def test_sagemaker_endpoint_metrics_variant_without_components(test):
    # an endpoint that hosts components reports its invocations against
    # them, so naming one of its variants that hosts none leaves nothing
    # to measure. Deciding that from the components left after the
    # dimensions are applied would make the endpoint look classic and ask
    # for a variant's invocations, which it never publishes.
    policy = test.load_policy(
        {'name': 'endpoints', 'resource': 'sagemaker-endpoint'})
    klass = SagemakerEndpoint.filter_registry.get('metrics')
    f = klass(
        {'type': 'metrics', 'name': 'Invocations', 'statistics': 'Sum',
         'value': 0, 'op': 'lte', 'dimensions': {'VariantName': 'quiet'}},
        policy.resource_manager)
    f.endpoint_components = {'e': ['component']}
    resource = {'EndpointName': 'e',
                'ProductionVariants': [{'VariantName': 'busy'},
                                       {'VariantName': 'quiet'}]}
    assert f.get_dimensions_set(resource) == []


# Metrics the endpoints in tests/terraform/sagemaker_endpoint_metrics don't
# produce, so there's nothing to record for them. The streaming metrics need
# a container that streams responses, ModelSetupTime a model load, and the
# multi-model metrics an endpoint hosting a model in MultiModel mode.
UNEXERCISED_METRICS = frozenset((
    'ModelSetupTime',
    'MidStreamErrors',
    'FirstChunkLatency',
    'FirstChunkModelLatency',
    'FirstChunkOverheadLatency',
    'ModelLoadingWaitTime',
    'ModelUnloadingTime',
    'ModelDownloadingTime',
    'ModelLoadingTime',
    'ModelCacheHit',
    'LoadedModelCount',
    ))


def sagemaker_endpoint_metric_entries():
    """Every (kind, metric) the catalogue describes for endpoints.

    Only the kinds an endpoint can be: metrics filed under no kind are
    loaded into every kind, so they show up under each of these.
    """
    return [
        pytest.param(kind, metric, published, id=f"{kind}-{metric}")
        for kind, by_resource in SAGEMAKER_METRICS.items()
        if kind is not None
        for metric, published in by_resource['sagemaker-endpoint'].items()
        ]


def sagemaker_endpoint_metric_entries_published():
    """The entries these endpoints can be recorded against."""
    return [
        entry if entry.values[1] not in UNEXERCISED_METRICS else
        pytest.param(*entry.values, id=entry.id,
                     marks=pytest.mark.skip(
                         reason='not produced by these endpoints'))
        for entry in sagemaker_endpoint_metric_entries()
        ]


@pytest.mark.parametrize('kind,metric,published',
                         sagemaker_endpoint_metric_entries())
def test_sagemaker_endpoint_metric_entry(test, kind, metric, published):
    # every entry the catalogue describes has to resolve, for the kind of
    # endpoint it's filed under, to that entry's namespace and to
    # dimensions the filter can actually supply
    policy = test.load_policy(
        {'name': 'endpoints', 'resource': 'sagemaker-endpoint'})
    klass = SagemakerEndpoint.filter_registry.get('metrics')
    f = klass({'type': 'metrics', 'name': metric, 'value': 0},
              policy.resource_manager)
    f.validate()

    endpoint = {'EndpointName': 'e',
                'ProductionVariants': [{'VariantName': 'AllTraffic'}]}
    f.endpoint_components = (
        {'e': ['component']} if kind == 'inference-component' else {})
    assert f.resource_kind(endpoint) == kind

    assert f.get_resource_namespace(endpoint) == published['namespace']

    dimensions_set = f.get_dimensions_set(endpoint)
    assert dimensions_set, f"{metric} resolved to no dimensions"
    assert {tuple(sorted(dimensions)) for dimensions in dimensions_set} == {
        names for names in published['dimension_sets']}
    assert all(isinstance(value, str)
               for dimensions in dimensions_set
               for value in dimensions.values())


# Metrics publish a minute or so after an invocation, and one publication
# window serves every case below, so the traffic is generated once for the
# whole module rather than per test.
INVOKED: list[str] = []

# variants and components of the endpoints tests/terraform/
# sagemaker_endpoint_metrics builds. "quiet" is deliberately left silent.
ENDPOINT_VARIANTS = {'busy': ('quiet', 'busy', 'gpu'),
                     'component': ('AllTraffic',)}


def invoke_for_metrics(test, factory, endpoints, components):
    """Give every endpoint something to report, once per recording run."""
    if not test.recording or INVOKED:
        return
    INVOKED.append('done')

    runtime = factory().client('sagemaker-runtime')
    for name, endpoint in endpoints.items():
        targets = [{'InferenceComponentName': component}
                   for component in components.get(endpoint, ())] or [
            {'TargetVariant': variant}
            for variant in ENDPOINT_VARIANTS[name]
            if variant != 'quiet'
            ]
        for target in targets:
            for _ in range(5):
                runtime.invoke_endpoint(
                    EndpointName=endpoint, ContentType='text/csv',
                    Body='1.0', **target)
    time.sleep(300)


@pytest.mark.audited
@pytest.mark.parametrize('kind,metric,published',
                         sagemaker_endpoint_metric_entries_published())
@terraform('sagemaker_endpoint_metrics', scope='module')
def test_sagemaker_endpoint_metric_published(
        test, sagemaker_endpoint_metrics, kind, metric, published):
    # every dimension set the catalogue names for a kind of endpoint has to
    # carry data for an endpoint of that kind. A set that isn't published
    # returns nothing, which no policy can tell from a quiet endpoint.
    endpoints = {
        name: sagemaker_endpoint_metrics[f'aws_sagemaker_endpoint.{name}.name']
        for name in ENDPOINT_VARIANTS
        }
    component = sagemaker_endpoint_metrics.outputs['component_name']['value']
    components = {endpoints['component']: [component]}

    factory = test.replay_flight_data(
        f"test_sagemaker_metric_{kind.replace('-', '_')}_{metric}")
    invoke_for_metrics(test, factory, endpoints, components)

    hosting = 'component' if kind == 'inference-component' else 'busy'
    resource = {
        'EndpointName': endpoints[hosting],
        'ProductionVariants': [{'VariantName': variant}
                               for variant in ENDPOINT_VARIANTS[hosting]],
        }

    p = test.load_policy(
        {'name': 'sagemaker-endpoint-metric',
         'resource': 'sagemaker-endpoint',
         'filters': [
             {'type': 'metrics', 'name': metric, 'statistics': 'Average',
              'days': 1, 'period': 3600, 'value': 0, 'op': 'gte'},
             ]},
        session_factory=factory,
        )
    f = p.resource_manager.filters[-1]
    # the components come from the module rather than a ListInferenceComponents
    # call, so each recording holds just the CloudWatch request
    f.endpoint_components = components

    assert f.process([resource]) == [resource]

    # one series per dimension set, and at least one carrying data: a
    # GPU metric has nothing for a variant with no GPU, which is why this
    # isn't every series
    series = resource['c7n.metrics']
    assert len(series) == len(f.get_dimensions_set(resource))
    assert any(points for points in series.values()), (
        f"{metric} returned no data for any {kind} dimension set")
