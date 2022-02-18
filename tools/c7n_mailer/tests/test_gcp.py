# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import unittest
from common import logger, MAILER_CONFIG_GCP, GCP_MESSAGE, GCP_MESSAGES
from c7n_mailer.gcp_mailer.gcp_queue_processor import MailerGcpQueueProcessor
from c7n_mailer.email_delivery import EmailDelivery
from c7n_mailer.utils import get_provider
from mock import patch


class GcpTest(unittest.TestCase):

    def setUp(self):
        self.compressed_message = GCP_MESSAGE
        self.loaded_message = json.loads(GCP_MESSAGE)

    @patch.object(EmailDelivery, 'send_c7n_email')
    def test_process_message(self, mock_email):
        mock_email.return_value = True
        processor = MailerGcpQueueProcessor(MAILER_CONFIG_GCP, logger)
        self.assertIsNone(processor.process_message(GCP_MESSAGES['receivedMessages'][0]))

    def test_receive(self):  # TODO: Set up GCP auth for test
        processor = MailerGcpQueueProcessor(MAILER_CONFIG_GCP, logger)
        messages = processor.receive_messages()
        self.assertEqual(messages, {})

    def test_ack(self):  # TODO: Set up GCP auth for test
        processor = MailerGcpQueueProcessor(MAILER_CONFIG_GCP, logger)
        self.assertEqual(processor.ack_messages('2019-05-13T18:31:17.926Z'), {})

    @patch.object(MailerGcpQueueProcessor, 'receive_messages')
    def test_run(self, mock_receive):
        mock_receive.return_value = []
        processor = MailerGcpQueueProcessor(MAILER_CONFIG_GCP, logger)
        processor.run()

    def test_is_gcp_cloud(self):
        self.assertEqual(get_provider(MAILER_CONFIG_GCP), 2)

    @patch('common.logger.info')
    @patch.object(MailerGcpQueueProcessor, 'receive_messages')
    def test_processor_run_logging(self, mock_receive, mock_log):
        mock_receive.return_value = []
        processor = MailerGcpQueueProcessor(MAILER_CONFIG_GCP, logger)
        processor.run()
        mock_log.assert_called_with('No messages left in the gcp topic subscription,'
                                    ' now exiting c7n_mailer.')
