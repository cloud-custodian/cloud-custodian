# Copyright 2015-2018 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import sys
import unittest

try:
    from azure.functions.queue import QueueMessage
except ImportError:
    pass

from azure_common import BaseTest
from c7n_azure.function import main as functionMain
from mock import patch


@unittest.skipIf(sys.version_info < (3, 6), "Functions is not supported in this version")
class FunctionTest(BaseTest):

    body = '{"data": "test body data",' \
           ' "subject": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/test"}'

    @patch('c7n_azure.handler.run')
    def test_queue_message_dequeue_count_less_than_max(self, mock_handler_run):
        input = QueueMessage(body=self.body,
                             dequeue_count=1,
                             )
        functionMain(input)

        mock_handler_run.assert_called_once()

    @patch('c7n_azure.handler.run')
    def test_queue_message_dequeue_count_above_max(self, mock_handler_run):
        input = QueueMessage(body=self.body,
                             dequeue_count=4)

        functionMain(input)

        mock_handler_run.assert_not_called()
