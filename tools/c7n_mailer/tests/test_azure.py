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

import copy
import unittest
import zlib
import base64
import json
from mock import MagicMock, patch
from common import MAILER_CONFIG_AZURE, ASQ_MESSAGE, logger
from c7n_mailer.azure_queue_processor import MailerAzureQueueProcessor

class AzureTest(unittest.TestCase):

    def setUp(self):
        self.compressed_message = MagicMock()
        self.compressed_message.content = base64.b64encode(zlib.compress(ASQ_MESSAGE))
        self.loaded_message = json.loads(ASQ_MESSAGE)

    @patch('c7n_mailer.sendgrid_delivery.SendGridDelivery.sendgrid_handler')
    @patch('c7n_mailer.sendgrid_delivery.SendGridDelivery.get_to_addrs_sendgrid_messages_map')
    def test_process_azure_queue_message_success(self, MockGetAddr, MockHandler):
        MockHandler.return_value = True
        MockGetAddr.return_value = 42

        # Run the process messages method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        self.assertTrue(azure_processor.process_azure_queue_message(self.compressed_message))

        # Verify mock calls were correct
        MockGetAddr.assert_called_with(self.loaded_message)
        MockHandler.assert_called_with(self.loaded_message, 42)

    @patch('c7n_mailer.sendgrid_delivery.SendGridDelivery.sendgrid_handler')
    @patch('c7n_mailer.sendgrid_delivery.SendGridDelivery.get_to_addrs_sendgrid_messages_map')
    def test_process_azure_queue_message_failure(self, MockGetAddr, MockHandler):
        MockHandler.return_value = False
        MockGetAddr.return_value = 42

        # Run the process messages method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        self.assertFalse(azure_processor.process_azure_queue_message(self.compressed_message))

        # Verify mock calls were correct
        MockGetAddr.assert_called_with(self.loaded_message)
        MockHandler.assert_called_with(self.loaded_message, 42)
