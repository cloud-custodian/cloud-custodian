# Copyright 2016 Capital One Services, LLC
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
import json
import os
import tempfile

from unittest import TestCase
from c7n.ufuncs import logsub


class TestLogsub(TestCase):

    def setUp(self):
        self.old_dir = os.getcwd()
        os.chdir(tempfile.gettempdir())
        self.config_data = {
            'test': 'data',
        }
        with open('config.json', 'w') as conf:
            json.dump(self.config_data, conf)

    def tearDown(self):
        os.remove('config.json')
        os.chdir(self.old_dir)

    def test_init(self):
        logsub.init()
        self.assertEqual(logsub.config, self.config_data)

    def test_message_event(self):
        event = {
            'message': 'This is a test',
            'timestamp': 1234567891011,
        }
        msg = logsub.message_event(event)
        # self.assertEqual(msg, 'Fri Feb 13 18:31:31 2009: This is a test')
        self.assertIn('Fri Feb 13', msg)
        self.assertIn('2009: This is a test', msg)
