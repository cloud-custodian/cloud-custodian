# Copyright 2016-2017 Capital One Services, LLC
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

from unittest import TestCase
from c7n.logs_support import _timestamp_from_string
from c7n.ufuncs import logsub


class TestLogsub(TestCase):

    def setUp(self):
        logsub.config = {"test": "data"}

    def test_message_event(self):
        event = {
            "message": "This is a test",
            "timestamp": _timestamp_from_string("Fri Feb 13 18:31:31 2009"),
        }
        msg = logsub.message_event(event)
        self.assertEqual(msg, "Fri Feb 13 18:31:31 2009: This is a test")
