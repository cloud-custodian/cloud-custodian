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



import unittest
from c7n.offhours import ScheduleParser, DEFAULT_TZ, VALID_DAYS



class ScheduleParserTest(unittest.TestCase):

    def setUp(self):
        self.parser = ScheduleParser()

    def test_parses_schedule(self):
        s = self.parser.parse('off=(m-f,19);on=(m-f,7);tz=pst')
        self.assertEquals(
            [{ 'days': ['m', 't', 'w', 'h', 'f'], 'hour': 19 }],
            s['off']
        )
        self.assertEquals(
            [{ 'days': ['m', 't', 'w', 'h', 'f'], 'hour': 7 }],
            s['on']
        )
        self.assertEquals('pst', s['tz'])

    def test_parses_bad_days_schedule(self):
        self.assertRaises(ValueError,
                          self.parser.parse,
                          'off=(m-z,19);on=(m-f,7);tz=pst')

        self.assertRaises(ValueError,
                          self.parser.parse,
                          'off=(m-f,19);on=(m-z,7);tz=pst')

    def test_parses_bad_hours_schedule(self):
        self.assertRaises(ValueError,
                          self.parser.parse,
                          'off=(m-f,19);on=(m-f,99);tz=pst')

        self.assertRaises(ValueError,
                          self.parser.parse,
                          'off=(m-f,99);on=(m-z,7);tz=pst')

        self.assertRaises(ValueError,
                          self.parser.parse,
                          'off=(m-f,19),(x,10);on=(m-f,1);tz=pst')

        self.assertRaises(ValueError,
                          self.parser.parse,
                          'off=(m-f,9);on=(m-z,7),(m,1,2);tz=pst')

    def test_parses_default_tz(self):
        s = self.parser.parse('off=(m-f,19);on=(m-f,7)')
        self.assertEquals(
            [{ 'days': ['m', 't', 'w', 'h', 'f'], 'hour': 19 }],
            s['off']
        )
        self.assertEquals(
            [{ 'days': ['m', 't', 'w', 'h', 'f'], 'hour': 7 }],
            s['on']
        )
        self.assertEquals(DEFAULT_TZ, s['tz'])

    def test_parses_multiple_hours(self):
        s = self.parser.parse('off=[(m-f,19),(s,9)];on=[(m-f,7),(s,15)];tz=pst')
        self.assertEquals(
            [
                { 'days': ['m', 't', 'w', 'h', 'f'], 'hour': 19 },
                { 'days': ['s'], 'hour': 9 }
            ],
            s['off']
        )
        self.assertEquals(
            [
                { 'days': ['m', 't', 'w', 'h', 'f'], 'hour': 7 },
                { 'days': ['s'], 'hour': 15 }
            ],
            s['on']
        )
        self.assertEquals('pst', s['tz'])

    def test_invalid_hour(self):
        self.assertRaises(ValueError,
                          self.parser.parse,
                          'off=(m-f,asdf);on=(m-f,asdf)')

    def test_invalid_day(self):
        self.assertRaises(ValueError,
                          self.parser.parse,
                          'off=(asdf,19);on=(asdf,7)')

    def test_valid_hour_range(self):
        self.assertEquals(True, self.parser.is_valid_hour_range(0))
        self.assertEquals(True, self.parser.is_valid_hour_range(12))
        self.assertEquals(True, self.parser.is_valid_hour_range(23))
        self.assertEquals(False, self.parser.is_valid_hour_range(24))
        self.assertEquals(False, self.parser.is_valid_hour_range(99))

    def test_valid_day(self):
        for d in VALID_DAYS:
            self.assertEquals(True, self.parser.is_valid_day(d))
        self.assertEquals(False, self.parser.is_valid_day("x"))
