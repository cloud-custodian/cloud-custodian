# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import json
import unittest
import zlib

from c7n_azure.storage_utils import StorageUtilities
from c7n_mailer.azure_mailer.azure_queue_processor import MailerAzureQueueProcessor
from c7n_mailer.azure_mailer.sendgrid_delivery import SendGridDelivery
from common import (
    MAILER_CONFIG_AZURE, ASQ_MESSAGE, ASQ_MESSAGE_TAG,
    ASQ_MESSAGE_SLACK, ASQ_MESSAGE_DATADOG, logger
)
from mock import MagicMock, patch, call


class AzureTest(unittest.TestCase):

    def setUp(self):
        self.compressed_message = MagicMock()
        self.compressed_message.content = base64.b64encode(
            zlib.compress(ASQ_MESSAGE.encode('utf8')))
        self.loaded_message = json.loads(ASQ_MESSAGE)

        self.tag_message = json.loads(ASQ_MESSAGE_TAG)

    @patch('c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery.sendgrid_handler')
    @patch('c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery'
           '.get_to_addrs_sendgrid_messages_map')
    def test_process_azure_queue_message_success(self, mock_get_addr, mock_handler):
        mock_handler.return_value = True
        mock_get_addr.return_value = 42

        # Run the process messages method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        self.assertTrue(azure_processor.process_azure_queue_message(self.compressed_message))

        # Verify mock calls were correct
        mock_get_addr.assert_called_with(self.loaded_message)
        mock_handler.assert_called_with(self.loaded_message, 42)

    @patch('c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery.sendgrid_handler')
    @patch('c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery'
           '.get_to_addrs_sendgrid_messages_map')
    def test_process_azure_queue_message_failure(self, mock_get_addr, mock_handler):
        mock_handler.return_value = False
        mock_get_addr.return_value = 42

        # Run the process messages method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        self.assertFalse(azure_processor.process_azure_queue_message(self.compressed_message))

        # Verify mock calls were correct
        mock_get_addr.assert_called_with(self.loaded_message)
        mock_handler.assert_called_with(self.loaded_message, 42)

    @patch.object(MailerAzureQueueProcessor, 'process_azure_queue_message')
    @patch.object(StorageUtilities, 'get_queue_client_by_uri')
    @patch.object(StorageUtilities, 'delete_queue_message')
    @patch.object(StorageUtilities, 'get_queue_messages')
    def test_run(self, mock_get_messages, mock_delete, mock_client, mock_process):
        mock_get_messages.side_effect = [[self.compressed_message], []]
        mock_client.return_value = (None, None)
        mock_process.return_value = True

        # Run the 'run' method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        azure_processor.run(False)

        self.assertEqual(2, mock_get_messages.call_count)
        self.assertEqual(1, mock_process.call_count)
        mock_delete.assert_called()

    @patch('sendgrid.SendGridAPIClient.send')
    def test_sendgrid_handler(self, mock_send):
        sendgrid_delivery = SendGridDelivery(MAILER_CONFIG_AZURE, logger)
        sendgrid_messages = \
            sendgrid_delivery.get_to_addrs_sendgrid_messages_map(self.loaded_message)
        result = sendgrid_delivery.sendgrid_handler(self.loaded_message, sendgrid_messages)
        self.assertTrue(result)
        mock_send.assert_called()

    @patch('c7n_mailer.azure_mailer.azure_queue_processor.SmtpDelivery')
    def test_smtp_delivery(self, mock_smtp):
        smtp_mailer_config = {
            'queue_url': 'asq://storageaccount.queue.core.windows.net/queuename',
            'from_address': 'you@youremail.com',
            'smtp_port': 25,
            'smtp_ssl': True,
            'smtp_server': 'test_server',
            'smtp_username': 'user',
            'smtp_password': 'password'
        }

        with patch('c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery'
                   '.get_to_addrs_sendgrid_messages_map',
                   return_value={('mock@test.com',): self.loaded_message}):
            azure_processor = MailerAzureQueueProcessor(smtp_mailer_config, logger)
            self.assertTrue(azure_processor.process_azure_queue_message(self.compressed_message))
            mock_smtp.assert_has_calls(
                [call().send_message(message=self.loaded_message, to_addrs=['mock@test.com'])])

    @patch('c7n_mailer.slack_delivery.SlackDelivery')
    def test_slack_delivery(self, mock_slack):
        slack_mailer_config = {
            'queue_url': 'asq://storageaccount.queue.core.windows.net/queuename',
            'slack_token': 'mock_token'
        }

        slack_compressed_message = MagicMock()
        slack_compressed_message.content = base64.b64encode(
            zlib.compress(ASQ_MESSAGE_SLACK.encode('utf8')))
        slack_loaded_message = json.loads(ASQ_MESSAGE_SLACK)

        mock_slack.return_value\
            .get_to_addrs_slack_messages_map.return_value = 'mock_slack_message_map'

        azure_processor = MailerAzureQueueProcessor(slack_mailer_config, logger)

        self.assertTrue(azure_processor.process_azure_queue_message(slack_compressed_message))
        mock_slack.assert_has_calls(
            [call().slack_handler(slack_loaded_message, 'mock_slack_message_map')])

    @patch('c7n_mailer.datadog_delivery.DataDogDelivery')
    def test_datadog_delivery(self, mock_datadog):
        datadog_mailer_config = {
            'queue_url': 'asq://storageaccount.queue.core.windows.net/queuename',
            'datadog_api_key': 'mock_api_key',
            'datadog_application_key': 'mock_application_key'
        }

        datadog_compressed_message = MagicMock()
        datadog_compressed_message.content = base64.b64encode(
            zlib.compress(ASQ_MESSAGE_DATADOG.encode('utf8')))
        datadog_loaded_message = json.loads(ASQ_MESSAGE_DATADOG)

        mock_datadog.return_value\
            .get_datadog_message_packages.return_value = 'mock_datadog_message_map'

        azure_processor = MailerAzureQueueProcessor(datadog_mailer_config, logger)

        self.assertTrue(azure_processor.process_azure_queue_message(datadog_compressed_message))
        mock_datadog.assert_has_calls(
            [call().deliver_datadog_messages('mock_datadog_message_map', datadog_loaded_message)])
