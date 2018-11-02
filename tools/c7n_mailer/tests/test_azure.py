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
from c7n_mailer.azure.azure_queue_processor import MailerAzureQueueProcessor
from c7n_mailer.azure.sendgrid_delivery import SendGridDelivery
from common import MAILER_CONFIG_AZURE, ASQ_MESSAGE, ASQ_MESSAGE_TAG, logger
from mock import MagicMock, patch


class AzureTest(unittest.TestCase):

    def setUp(self):
        self.compressed_message = MagicMock()
        self.compressed_message.content = base64.b64encode(
            zlib.compress(ASQ_MESSAGE.encode('utf8')))
        self.loaded_message = json.loads(ASQ_MESSAGE)

        self.tag_message = json.loads(ASQ_MESSAGE_TAG)

    @patch('c7n_mailer.azure.sendgrid_delivery.SendGridDelivery.sendgrid_handler')
    @patch('c7n_mailer.azure.sendgrid_delivery.SendGridDelivery.get_to_addrs_sendgrid_messages_map')
    def test_process_azure_queue_message_success(self, mock_get_addr, mock_handler):
        mock_handler.return_value = True
        mock_get_addr.return_value = 42

        # Run the process messages method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        self.assertTrue(azure_processor.process_azure_queue_message(self.compressed_message))

        # Verify mock calls were correct
        mock_get_addr.assert_called_with(self.loaded_message)
        mock_handler.assert_called_with(self.loaded_message, 42)

    @patch('c7n_mailer.azure.sendgrid_delivery.SendGridDelivery.sendgrid_handler')
    @patch('c7n_mailer.azure.sendgrid_delivery.SendGridDelivery.get_to_addrs_sendgrid_messages_map')
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

    def test_get_email_to_addrs_to_resources_map_tag(self):
        delivery = SendGridDelivery(MAILER_CONFIG_AZURE, logger)
        result_map = delivery.get_email_to_addrs_to_resources_map(self.tag_message)
        self.assertEqual(list(result_map.keys())[0][0], 'user@domain.com')

    def test_get_email_to_addrs_to_resources_map_null_tag(self):
        delivery = SendGridDelivery(MAILER_CONFIG_AZURE, logger)

        # null out tags
        message = self.tag_message
        message['resources'][0]['tags'] = {}

        result_map = delivery.get_email_to_addrs_to_resources_map(message)
        self.assertEqual(len(result_map.keys()), 0)
