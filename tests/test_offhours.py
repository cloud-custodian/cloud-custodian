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
import datetime
from dateutil import zoneinfo

from mock import mock

from .common import BaseTest, instance

from c7n.offhours import OffHour, OnHour


# Per http://blog.xelnor.net/python-mocking-datetime/
# naive implementation has issues with pypy

real_datetime_class = datetime.datetime


def mock_datetime_now(tgt, dt):

    class DatetimeSubclassMeta(type):
        @classmethod
        def __instancecheck__(mcs, obj):
            return isinstance(obj, real_datetime_class)

    class BaseMockedDatetime(real_datetime_class):
        target = tgt

        @classmethod
        def now(cls, tz=None):
            return cls.target.replace(tzinfo=tz)

        @classmethod
        def utcnow(cls):
            return cls.target

        # Python2 & Python3 compatible metaclass

    MockedDatetime = DatetimeSubclassMeta(
        'datetime', (BaseMockedDatetime,), {})
    return mock.patch.object(dt, 'datetime', MockedDatetime)


class OffHoursFilterTest(BaseTest):

    def test_opt_out_behavior(self):
        # Some users want to match based on policy filters to
        # a resource subset with default opt out behavior
        t = datetime.datetime(
            year=2015, month=12, day=1, hour=19, minute=5,
            tzinfo=zoneinfo.gettz('America/New_York'))
        i = instance(Tags=[])
        f = OffHour({'opt-out': True})

        with mock_datetime_now(t, datetime):
            self.assertEqual(f(i), True)
            t = datetime.datetime(
                year=2015, month=12, day=1, hour=7, minute=5,
                tzinfo=zoneinfo.gettz('America/New_York'))
            f = OnHour({})
            #self.assertEqual(f(i), True)

    def test_opt_in_behavior(self):
        # Given the addition of opt out behavior, verify if its
        # not configured that we don't touch an instance that
        # has no downtime tag
        t = datetime.datetime(
            year=2015, month=12, day=1, hour=19, minute=5,
            tzinfo=zoneinfo.gettz('America/New_York'))
        i = instance(Tags=[])
        f = OffHour({})

        with mock_datetime_now(t, datetime):
            self.assertEqual(f(i), False)
            t = datetime.datetime(
                year=2015, month=12, day=1, hour=7, minute=5,
                tzinfo=zoneinfo.gettz('America/New_York'))
            f = OnHour({})
            self.assertEqual(f(i), False)

    def test_time_match_stops_after_skew(self):
        hour = 7
        t = datetime.datetime(
            year=2015, month=12, day=1, hour=hour, minute=5,
            tzinfo=zoneinfo.gettz('America/New_York'))
        i = instance(Tags=[
            {'Key': 'maid_offhours', 'Value': 'tz=est'}])
        f = OnHour({'skew': 1})
        results = []

        with mock_datetime_now(t, datetime) as dt:
            for n in range(0, 4):
                dt.target = t.replace(hour=hour+n)
                results.append(f(i))
        self.assertEqual(results, [True, True, False, False])

    def test_onhour_weekend_support(self):
        start_day = 26
        t = datetime.datetime(
            year=2016, day=start_day, month=2, hour=7, minute=20)
        i = instance(Tags=[{'Key': 'maid_offhours', 'Value': 'tz=est'}])
        f = OnHour({})
        results = []
        with mock_datetime_now(t, datetime) as dt:

            for n in range(0, 4):
                dt.target = t.replace(day=start_day+n)
                results.append(f(i))
        self.assertEqual(results, [True, False, False, True])

    def test_offhour_weekend_support(self):
        start_day = 26
        t = datetime.datetime(
            year=2016, day=start_day, month=2, hour=19, minute=20)
        i = instance(Tags=[{'Key': 'maid_offhours', 'Value': 'tz=est'}])
        f = OffHour({})
        results = []
        with mock_datetime_now(t, datetime) as dt:
            for n in range(0, 4):
                dt.target = t.replace(day=start_day+n)
                results.append(f(i))
        self.assertEqual(results, [True, False, False, True])

    def test_current_time_test(self):
        t = datetime.datetime.now(zoneinfo.gettz('America/New_York'))
        t = t.replace(year=2015, month=12, day=1, hour=19, minute=5)
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[
                {'Key': 'maid_offhours', 'Value': 'tz=est'}])
            f = OffHour({})
            p = f.get_tag_parts(i)
            self.assertEqual(p, (['tz=est'], {'maid_offhours': 'tz=est'}))
            tz = f.get_local_tz(p[0])
            self.assertEqual(str(tz), "tzfile('America/New_York')")
            self.assertEqual(
                datetime.datetime.now(tz), t)
            self.assertEqual(t.hour, 19)

    def test_offhours_real_world_values(self):
        t = datetime.datetime.now(zoneinfo.gettz('America/New_York'))
        t = t.replace(year=2015, month=12, day=1, hour=19, minute=5)
        with mock_datetime_now(t, datetime):
            for i in [
                    instance(Tags=[
                        {'Key': 'maid_offhours', 'Value': ''}]),
                    instance(Tags=[
                        {'Key': 'maid_offhours', 'Value': '"Offhours tz=ET"'}]),
                    instance(Tags=[
                        {'Key': 'maid_offhours', 'Value': 'Offhours tz=PT'}])]:
                self.assertEqual(OffHour({})(i), True)

    def test_offhours(self):
        t = datetime.datetime(year=2015, month=12, day=1, hour=19, minute=5,
                              tzinfo=zoneinfo.gettz('America/New_York'))
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[
                {'Key': 'maid_offhours', 'Value': 'tz=est'}])
            self.assertEqual(OffHour({})(i), True)

    def test_onhour(self):
        t = datetime.datetime(year=2015, month=12, day=1, hour=7, minute=5,
                              tzinfo=zoneinfo.gettz('America/New_York'))
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[
                {'Key': 'maid_offhours', 'Value': 'tz=est'}])
            self.assertEqual(OnHour({})(i), True)
            self.assertEqual(OnHour({'onhour': 8})(i), False)

    def test_cant_parse_tz(self):
        i = instance(Tags=[
            {'Key': 'maid_offhours', 'Value': 'tz=evt'}])
        self.assertEqual(OffHour({})(i), False)
