# Copyright 2019 Capital One Services, LLC
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
from common import logger, MAILER_CONFIG, GCP_MESSAGE
from c7n_mailer.gcp.gcp_pubsub_processor import MailerGcpPubSubProcessor
from mock import MagicMock, patch


class GcpTest(unittest.TestCase):

    def setUp(self):
        self.compressed_message = MagicMock()
        self.compressed_message.content = base64.b64encode(
            zlib.compress(GCP_MESSAGE.encode('utf8')))
        self.loaded_message = json.loads(GCP_MESSAGE)

    @patch('c7n_mailer.email_delivery.get_to_addrs_email_messages_map')
    def test_process_azure_queue_message_success(self, mock_get_addr):
        p = MailerGcpPubSubProcessor(MAILER_CONFIG, logger)
        self.assertTrue(p.process_message(self.compressed_message))
        mock_get_addr.assert_called_with(self.loaded_message)

    @patch('c7n_mailer.email_delivery.get_to_addrs_email_messages_map')
    def test_process_azure_queue_message_failure(self, mock_get_addr):
        p = MailerGcpPubSubProcessor(MAILER_CONFIG, logger)
        self.assertFalse(p.process_message(self.compressed_message))
        mock_get_addr.assert_called_with(self.loaded_message)

    @patch.object(MailerGcpPubSubProcessor, 'process_message')
    @patch.object(MailerGcpPubSubProcessor, 'ack_messages')
    @patch.object(MailerGcpPubSubProcessor, 'receive_messages')
    def test_run(self, mock_get_message, mock_ack, mock_process):
        mock_get_message.side_effect = [[self.compressed_message], []]
        mock_ack.return_value = True
        mock_process.return_value = True
        p = MailerGcpPubSubProcessor(MAILER_CONFIG, logger)
        p.run()
        self.assertEqual(2, mock_get_message.call_count)
        self.assertEqual(1, mock_process.call_count)
        mock_ack.assert_called()
