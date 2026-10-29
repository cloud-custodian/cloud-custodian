# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
# -*- coding: utf-8 -*-
import argparse
import unittest
import logging
import os
import tempfile
import boto3
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from c7n_mailer import replay
from c7n_mailer import handle
from c7n_mailer import sqs_queue_processor
from c7n_mailer import cli
from c7n_mailer import deploy
from c7n_mailer.azure_mailer import azure_queue_processor
from c7n_mailer.gcp_mailer import gcp_queue_processor
from c7n.mu import PythonPackageArchive, SQSSubscription
from c7n.utils import reset_session_cache
from common import MAILER_CONFIG, MAILER_CONFIG_GCP, MAILER_CONFIG_AZURE, SQS_MESSAGE_1_ENCODED


class AWSMailerTests(unittest.TestCase):
    def test_replay_parser_creation(self):
        parser = replay.setup_parser()
        self.assertIs(parser.__class__, argparse.ArgumentParser)

    def test_mailer_handle(self):
        handle.start_c7n_mailer(logging.getLogger("c7n_mailer"), MAILER_CONFIG, False)
        http_proxy = "username:password@my.proxy.com:80"
        https_proxy = "username:password@my.proxy.com:443"
        MAILER_CONFIG["http_proxy"] = http_proxy
        MAILER_CONFIG["https_proxy"] = https_proxy
        config = handle.config_setup(MAILER_CONFIG)
        self.assertEqual(
            [config.get("http_proxy"), config.get("https_proxy")], [http_proxy, https_proxy]
        )
        # Clear http proxy
        MAILER_CONFIG["http_proxy"] = ""
        MAILER_CONFIG["https_proxy"] = ""
        config = handle.config_setup(MAILER_CONFIG)

    @patch("c7n_mailer.target.EmailDelivery")
    @patch("c7n_mailer.sns_delivery.SnsDelivery")
    def test_sqs_queue_processor(self, mock_sns_delivery, mock_email_delivery):
        mailer_sqs_queue_processor = sqs_queue_processor.MailerSqsQueueProcessor(
            MAILER_CONFIG, boto3.Session(), logging.getLogger("c7n_mailer")
        )
        self.assertIs(
            mailer_sqs_queue_processor.__class__, sqs_queue_processor.MailerSqsQueueProcessor
        )

        mailer_sqs_queue_processor.process_sqs_message(SQS_MESSAGE_1_ENCODED)
        assert mock_sns_delivery.called

    @patch("c7n_mailer.target.EmailDelivery")
    @patch("c7n_mailer.sns_delivery.SnsDelivery")
    def test_sqs_queue_processor_lambda_event(self, mock_sns_delivery, mock_email_delivery):
        processor = sqs_queue_processor.MailerSqsQueueProcessor(
            MAILER_CONFIG, boto3.Session(), logging.getLogger("c7n_mailer")
        )
        good = {
            "messageId": "good",
            "body": SQS_MESSAGE_1_ENCODED["Body"].decode("ascii"),
            "attributes": {"SentTimestamp": "1672574400000"},
            "messageAttributes": {
                "mtype": {"stringValue": sqs_queue_processor.DATA_MESSAGE, "dataType": "String"}
            },
        }
        bad = {"messageId": "bad", "body": "not a custodian message"}
        result = processor.process_event({"Records": [good, bad]})
        # Only the failed message is reported, so lambda deletes the other one from the queue.
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "bad"}]})
        assert mock_sns_delivery.called

    @patch("c7n_mailer.handle.MailerSqsQueueProcessor")
    def test_mailer_handle_sqs(self, mock_processor):
        mock_processor.return_value.process_event.return_value = {"batchItemFailures": []}
        event = {"Records": []}
        result = handle.start_c7n_mailer_sqs(logging.getLogger("c7n_mailer"), event, MAILER_CONFIG)
        self.assertEqual(result, {"batchItemFailures": []})
        mock_processor.return_value.process_event.assert_called_once_with(event)

    def test_azure_queue_processor(self):
        processor = azure_queue_processor.MailerAzureQueueProcessor(
            MAILER_CONFIG_AZURE, logging.getLogger("c7n_mailer")
        )
        self.assertIs(processor.__class__, azure_queue_processor.MailerAzureQueueProcessor)

    def test_gcp_queue_processor(self):
        processor = gcp_queue_processor.MailerGcpQueueProcessor(
            MAILER_CONFIG_GCP, logging.getLogger("c7n_mailer")
        )
        self.assertIs(processor.__class__, gcp_queue_processor.MailerGcpQueueProcessor)

    def test_cli_run(self):
        # Generate loggers and make sure they have the right class, for codecov
        self.assertEqual(cli.get_logger().__class__, logging.Logger)
        self.assertEqual(cli.get_logger(True).__class__, logging.Logger)
        parser = cli.get_c7n_mailer_parser()
        self.assertIs(parser.__class__, argparse.ArgumentParser)
        session = cli.session_factory(MAILER_CONFIG)
        self.assertEqual([session.region_name, session.profile_name], ["us-east-1", "default"])


class DeployTests(unittest.TestCase):
    def test_get_archive(self):
        archive = deploy.get_archive({"templates_folders": []})
        assert isinstance(archive, PythonPackageArchive)
        # basic sanity checks using random, low values
        assert archive.size > 10000  # this should really be about 1.5 MB
        assert len(archive.get_filenames()) > 50  # should be > 500

    def test_get_archive_with_templates(self):
        with (
            tempfile.TemporaryDirectory() as template_folder1,
            tempfile.TemporaryDirectory() as template_folder2,
            tempfile.TemporaryDirectory() as template_folder3,
        ):

            with open(os.path.join(template_folder1, "beta.j2"), "w") as f:
                f.write("beta")
            with open(os.path.join(template_folder2, "gamma.j2"), "w") as f:
                f.write("gamma")
            with open(os.path.join(template_folder3, "alpha.j2"), "w") as f:
                f.write("alpha")
            # Test with multiple template folders
            config = {"templates_folders": [template_folder1, template_folder2, template_folder3]}
            # Ensure checksum is the same with multiple calls
            archive1 = deploy.get_archive(config)
            checksum1 = archive1.get_checksum()
            archive2 = deploy.get_archive(config)
            checksum2 = archive2.get_checksum()
            assert checksum1 == checksum2
            archive1.remove()
            archive2.remove()


@patch("c7n_mailer.deploy.LambdaManager")
@patch("c7n_mailer.deploy.get_archive")
class ProvisionTests(unittest.TestCase):
    queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/mailer"
    queue_arn = "arn:aws:sqs:us-east-1:123456789012:mailer"

    def setUp(self):
        reset_session_cache()
        self.addCleanup(reset_session_cache)
        self.session = MagicMock()
        self.sqs = MagicMock()
        self.sqs.get_queue_attributes.return_value = {"Attributes": {"QueueArn": self.queue_arn}}
        self.lambda_client = MagicMock()
        self.lambda_client.list_event_source_mappings.return_value = {"EventSourceMappings": []}
        self.session.client.side_effect = lambda service, **kw: {
            "sqs": self.sqs,
            "lambda": self.lambda_client,
        }.get(service, MagicMock())

    def config(self, **kw):
        config = {
            "queue_url": self.queue_url,
            "role": "arn:aws:iam::123456789012:role/mailer",
            "runtime": "python3.12",
            "memory": 1024,
            "timeout": 300,
            "subnets": None,
            "security_groups": None,
        }
        config.update(kw)
        return config

    def published(self, manager):
        return manager.return_value.publish.call_args[0][0]

    @patch("c7n_mailer.deploy.CloudWatchEventSource.remove")
    def test_provision_sqs_trigger(self, remove_schedule, get_archive, manager):
        deploy.provision(
            self.config(lambda_trigger="sqs", lambda_sqs_batch_size=5), lambda: self.session
        )
        func = self.published(manager)
        self.assertEqual(func.handler, "periodic.sqs_dispatch")
        [subscription] = func.get_events(lambda: self.session)
        self.assertIsInstance(subscription, SQSSubscription)
        self.assertEqual(subscription.queue_arns, [self.queue_arn])
        self.assertEqual(subscription.batch_size, 5)
        self.assertEqual(subscription.response_types, ["ReportBatchItemFailures"])
        # the periodic rule of an earlier deployment is removed
        remove_schedule.assert_called_once_with(func, func_deleted=False)

    def test_provision_schedule_removes_sqs_trigger(self, get_archive, manager):
        other_queue = "arn:aws:sqs:us-east-1:123456789012:other"
        self.lambda_client.list_event_source_mappings.return_value = {
            "EventSourceMappings": [
                {"UUID": "mailer-uuid", "EventSourceArn": self.queue_arn},
                {"UUID": "other-uuid", "EventSourceArn": other_queue},
            ]
        }
        deploy.provision(self.config(), lambda: self.session)
        func = self.published(manager)
        self.assertEqual(func.handler, "periodic.dispatch")
        self.sqs.get_queue_attributes.assert_not_called()
        # only the trigger on the mailer queue is removed
        self.lambda_client.delete_event_source_mapping.assert_called_once_with(UUID="mailer-uuid")

    def test_provision_schedule_without_list_permission(self, get_archive, manager):
        self.lambda_client.list_event_source_mappings.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "ListEventSourceMappings",
        )
        deploy.provision(self.config(), lambda: self.session)
        manager.return_value.publish.assert_called_once()
        self.lambda_client.delete_event_source_mapping.assert_not_called()
