# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
# -*- coding: utf-8 -*-
import argparse
import unittest
import logging
import os
import tempfile
import boto3
from unittest.mock import patch

from c7n_mailer import replay
from c7n_mailer import handle
from c7n_mailer import sqs_queue_processor
from c7n_mailer import cli
from c7n_mailer import deploy
from c7n_mailer.azure_mailer import azure_queue_processor
from c7n_mailer.gcp_mailer import gcp_queue_processor
from c7n.mu import PythonPackageArchive
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

            # Use multiple folders to test ordering
            config = {"templates_folders": [template_folder1, template_folder2, template_folder3]}

            archive1 = deploy.get_archive(config)
            checksum1 = archive1.get_checksum()
            archive2 = deploy.get_archive(config)
            checksum2 = archive2.get_checksum()
            assert checksum1 == checksum2, "Checksums should be equal"
            archive1.remove()
            archive2.remove()
