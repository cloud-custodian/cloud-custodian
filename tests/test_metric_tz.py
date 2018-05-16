# Copyright 2017 Capital One Services, LLC
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

import unittest

from .common import BaseTest

import datetime
from c7n.output import MetricsOutput


class metrics_log_test(BaseTest):

    def test_output_tz(self):

        output = MetricsOutput(None)
        self.change_environment()
        now = datetime.datetime.utcnow()
        output_time = output.get_timestamp()

        self.assertEqual(now.hour, output_time.hour)
        self.assertEqual(now.minute, output_time.minute)

        self.change_environment(C7N_METRICS_TZ="False")
        now_utc = datetime.datetime.now()

        output_time = output.get_timestamp()

        self.assertEqual(now_utc.hour, output_time.hour)
        self.assertEqual(now_utc.minute, output_time.minute)


if __name__ == "__main__":
    unittest.main()
