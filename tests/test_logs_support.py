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
from __future__ import absolute_import, division, print_function, unicode_literals

import os

from unittest import TestCase

from c7n.logs_support import (
    normalized_log_entries,
    log_entries_in_range,
    _timestamp_from_string,
)


def log_lines():
    with open(
        os.path.join(
            os.path.dirname(__file__),
            'data',
            'logs',
            'test-policy',
            'custodian-run.log',
        )
    ) as fh:
        return fh.readlines()


class TestLogsSupport(TestCase):

    def test_normailization(self):
        raw_entries = log_lines()
        log_gen = normalized_log_entries(raw_entries)
        nrm_entries = list(log_gen)
        # multi-line entries are being combined
        self.assertEqual(len(raw_entries), 144)
        self.assertEqual(len(nrm_entries), 55)
        # entries look reasonable
        entry = nrm_entries[1]
        self.assertIn('timestamp', entry)
        self.assertIn('message', entry)
        self.assertIsInstance(entry['timestamp'], long)
        self.assertIsInstance(entry['message'], unicode)

    def test_entries_in_range(self):
        raw_entries = log_lines()
        log_gen = normalized_log_entries(raw_entries)
        nrm_entries = list(log_gen)
        range_gen = log_entries_in_range(
            nrm_entries,
            '2016-11-21 12:40:00',
            '2016-11-21 12:45:00',
        )
        in_range = list(range_gen)
        # fewer entries than we started with
        self.assertLess(len(in_range), len(nrm_entries))
        # entries are within 5 minutes of each other
        span = (in_range[-1]['timestamp'] - in_range[0]['timestamp']) / 1000
        self.assertLess(span, 300)

    def test_timestamp_from_string(self):
        tfs = _timestamp_from_string
        date_text = '2016-11-21 13:13:41'
        self.assertIsInstance(tfs(date_text), long)
        self.assertEqual(tfs('not a date'), 0)
