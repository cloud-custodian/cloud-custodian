# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest

from c7n.resources.sagemaker import SagemakerJobQueryParser, CompilationJobQueryParser
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
