# Copyright 2015-2017 Capital One Services, LLC
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

import datetime
import json
import os

from dateutil import zoneinfo

from mock import mock

from .common import BaseTest, instance

from c7n.exceptions import PolicyValidationError
from c7n.filters.offhours import OffHour, OnHour, ScheduleParser, Time


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
        b"datetime" if str is bytes else "datetime",  # hack Python2/3 port
        (BaseMockedDatetime,),
        {},
    )
    return mock.patch.object(dt, "datetime", MockedDatetime)


class OffHoursFilterTest(BaseTest):
    """[off|on] hours testing"""

    def test_offhours_records(self):
        session_factory = self.replay_flight_data("test_offhours_records")
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=8, day=14, hour=19, minute=00)

        with mock_datetime_now(t, datetime):
            p = self.load_policy(
                {
                    "name": "offhours-records",
                    "resource": "ec2",
                    "filters": [
                        {"State.Name": "running"},
                        {
                            "type": "offhour",
                            "offhour": 19,
                            "tag": "custodian_downtime",
                            "default_tz": "est",
                            "weekends": False,
                        },
                    ],
                },
                session_factory=session_factory,
            )
            resources = p.run()
        self.assertEqual(resources, [])
        with open(
            os.path.join(
                p.options["output_dir"], "offhours-records", "parse_errors.json"
            )
        ) as fh:
            data = json.load(fh)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0][0], "i-0ee3a9bc2eeed269f")
            self.assertEqual(data[0][1], "off=[m-f,8];on=[n-f,5];pz=est")
        with open(
            os.path.join(p.options["output_dir"], "offhours-records", "opted_out.json")
        ) as fh:
            data = json.load(fh)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["InstanceId"], "i-0a619b58a7e704a9f")

    def test_validate(self):
        url_test = "s3://test-dest/holidays.csv"
        self.assertRaises(
            PolicyValidationError, OffHour({"default_tz": "zmta"}).validate
        )
        self.assertRaises(PolicyValidationError, OffHour({"offhour": 25}).validate)
        self.assertRaises(
            PolicyValidationError,
            OffHour(
                {
                    "skip-days": ["2017-01-01"],
                    "skip-days-from": {"expr": 0, "format": "csv", "url": url_test},
                }
            ).validate,
        )
        i = OffHour({})
        self.assertEqual(i.validate(), i)

    def test_process(self):
        f = OffHour({"opt-out": True})
        instances = [
            instance(Tags=[]),
            instance(Tags=[{"Key": "maid_offhours", "Value": ""}]),
            instance(Tags=[{"Key": "maid_offhours", "Value": "on"}]),
            instance(Tags=[{"Key": "maid_offhours", "Value": "off"}]),
            instance(
                Tags=[
                    {
                        "Key": "maid_offhours",
                        "Value": "off=(m-f,5);zebrablue,on=(t-w,5)",
                    }
                ]
            ),
        ]
        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=19,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        with mock_datetime_now(t, datetime):
            self.assertEqual(
                f.process(instances), [instances[0], instances[1], instances[2]]
            )

    def test_opt_out_behavior(self):
        # Some users want to match based on policy filters to
        # a resource subset with default opt out behavior
        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=19,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        f = OffHour({"opt-out": True})

        with mock_datetime_now(t, datetime):
            i = instance(Tags=[])
            self.assertEqual(f(i), True)
            i = instance(Tags=[{"Key": "maid_offhours", "Value": ""}])
            self.assertEqual(f(i), True)
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "on"}])
            self.assertEqual(f(i), True)
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "off"}])
            self.assertEqual(f(i), False)
            self.assertEqual(f.opted_out, [i])

    def test_opt_in_behavior(self):
        # Given the addition of opt out behavior, verify if its
        # not configured that we don't touch an instance that
        # has no downtime tag
        i = instance(Tags=[])
        i2 = instance(Tags=[{"Key": "maid_offhours", "Value": ""}])
        i3 = instance(Tags=[{"Key": "maid_offhours", "Value": "on"}])

        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=19,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        f = OffHour({})

        with mock_datetime_now(t, datetime):
            self.assertEqual(f(i), False)
            self.assertEqual(f(i2), True)
            self.assertEqual(f(i3), True)

        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=7,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        f = OnHour({})

        with mock_datetime_now(t, datetime):
            self.assertEqual(f(i), False)
            self.assertEqual(f(i2), True)
            self.assertEqual(f(i3), True)

    def xtest_time_match_stops_after_skew(self):
        hour = 7
        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=hour,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
        f = OnHour({"skew": 1})
        results = []

        with mock_datetime_now(t, datetime) as dt:
            for n in range(0, 4):
                dt.target = t.replace(hour=hour + n)
                results.append(f(i))
        self.assertEqual(results, [True, True, False, False])

    def test_resource_schedule_error(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2015, month=12, day=1, hour=19, minute=5)
        f = OffHour({})
        f.process_resource_schedule = lambda: False
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
            self.assertEqual(f(i), False)

    def test_time_filter_usage_errors(self):
        self.assertRaises(NotImplementedError, Time, {})

    def test_everyday_onhour(self):
        # weekends on means we match times on the weekend
        start_day = 14  # sunday
        t = datetime.datetime(year=2016, day=start_day, month=8, hour=7, minute=20)
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
        f = OnHour({"weekends": False})
        results = []
        with mock_datetime_now(t, datetime) as dt:
            for n in range(7):
                dt.target = t.replace(day=start_day + n)
                results.append(f(i))
        self.assertEqual(results, [True] * 7)

    def test_everyday_offhour(self):
        # weekends on means we match times on the weekend
        start_day = 14  # sunday
        t = datetime.datetime(year=2016, day=start_day, month=8, hour=19, minute=20)
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
        f = OffHour({"weekends": False})
        results = []
        with mock_datetime_now(t, datetime) as dt:
            for n in range(7):
                dt.target = t.replace(day=start_day + n)
                results.append(f(i))
        self.assertEqual(results, [True] * 7)

    def test_weekends_only_onhour_support(self):
        # start day is a sunday, weekend only means we only start
        # on monday morning.
        start_day = 14
        t = datetime.datetime(year=2016, day=start_day, month=8, hour=7, minute=20)
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
        f = OnHour({"weekends-only": True})
        results = []
        with mock_datetime_now(t, datetime) as dt:
            for n in range(7):
                dt.target = t.replace(day=start_day + n)
                results.append(f(i))
        self.assertEqual(results, [False, True, False, False, False, False, False])

    def test_weekends_only_offhour_support(self):
        # start day is a sunday, weekend only means we only stop
        # on friday evening.
        start_day = 14
        t = datetime.datetime(year=2016, day=start_day, month=8, hour=7, minute=20)
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
        f = OnHour({"weekends-only": True})
        results = []
        with mock_datetime_now(t, datetime) as dt:
            for n in range(7):
                dt.target = t.replace(day=start_day + n)
                results.append(f(i))
        self.assertEqual(results, [False, True, False, False, False, False, False])

    def test_onhour_weekend_support(self):
        start_day = 14
        t = datetime.datetime(year=2016, day=start_day, month=2, hour=19, minute=20)
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
        f = OffHour({"weekends-only": True})
        results = []
        with mock_datetime_now(t, datetime) as dt:
            for n in range(7):
                dt.target = t.replace(day=start_day + n)
                results.append(f(i))
        self.assertEqual(results, [False, False, False, False, False, True, False])

    def test_offhour_weekend_support(self):
        start_day = 26
        t = datetime.datetime(year=2016, day=start_day, month=2, hour=19, minute=20)
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
        f = OffHour({})
        results = []
        with mock_datetime_now(t, datetime) as dt:
            for n in range(0, 4):
                dt.target = t.replace(day=start_day + n)
                results.append(f(i))
        self.assertEqual(results, [True, False, False, True])

    def test_current_time_test(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2015, month=12, day=1, hour=19, minute=5)
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
            f = OffHour({})
            p = f.get_tag_value(i)
            self.assertEqual(p, "tz=est")
            tz = f.get_tz("est")
            self.assertTrue(
                str(tz) in ("tzfile('US/Eastern')", "tzfile('America/New_York')")
            )
            self.assertEqual(datetime.datetime.now(tz), t)
            self.assertEqual(t.hour, 19)

    def test_offhours_real_world_values(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2015, month=12, day=1, hour=19, minute=5)
        with mock_datetime_now(t, datetime):
            results = [
                OffHour({})(i)
                for i in [
                    instance(Tags=[{"Key": "maid_offhours", "Value": ""}]),
                    instance(Tags=[{"Key": "maid_offhours", "Value": "on"}]),
                    instance(
                        Tags=[{"Key": "maid_offhours", "Value": '"Offhours tz=ET"'}]
                    ),
                    instance(
                        Tags=[{"Key": "maid_offhours", "Value": "Offhours tz=PT"}]
                    ),
                ]
            ]
            # unclear what this is really checking
            self.assertEqual(results, [True, True, True, True])

    def test_offhours_get_value(self):
        off = OffHour({"default_tz": "ct"})
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "Offhours tz=PT"}])
        self.assertEqual(off.get_tag_value(i), "offhours tz=pt")
        self.assertFalse(off.parser.has_resource_schedule(off.get_tag_value(i), "off"))
        self.assertTrue(off.parser.keys_are_valid(off.get_tag_value(i)))
        self.assertEqual(off.parser.raw_data(off.get_tag_value(i)), {"tz": "pt"})

    def test_offhours(self):
        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=19,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
            self.assertEqual(OffHour({})(i), True)

    def test_onhour(self):
        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=7,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
            self.assertEqual(OnHour({})(i), True)
            self.assertEqual(OnHour({"onhour": 8})(i), False)

    def test_cant_parse_tz(self):
        i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=evt"}])
        self.assertEqual(OffHour({})(i), False)

    def test_custom_offhours(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=5, day=26, hour=19, minute=00)
        results = []

        with mock_datetime_now(t, datetime):
            for i in [
                instance(
                    Tags=[
                        {
                            "Key": "maid_offhours",
                            "Value": "off=(m-f,19);on=(m-f,7);tz=et",
                        }
                    ]
                ),
                instance(
                    Tags=[
                        {
                            "Key": "maid_offhours",
                            "Value": "off=(m-f,20);on=(m-f,7);tz=et",
                        }
                    ]
                ),
            ]:
                results.append(OffHour({})(i))
            self.assertEqual(results, [True, False])

    def test_custom_onhours(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=5, day=26, hour=7, minute=00)
        results = []

        with mock_datetime_now(t, datetime):
            for i in [
                instance(
                    Tags=[
                        {
                            "Key": "maid_offhours",
                            "Value": "off=(m-f,19);on=(m-f,7);tz=et",
                        }
                    ]
                ),
                instance(
                    Tags=[
                        {
                            "Key": "maid_offhours",
                            "Value": "off=(m-f,20);on=(m-f,9);tz=et",
                        }
                    ]
                ),
            ]:
                results.append(OnHour({})(i))
            self.assertEqual(results, [True, False])

    def test_arizona_tz(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=5, day=26, hour=7, minute=00)
        with mock_datetime_now(t, datetime):
            i = instance(
                Tags=[
                    {"Key": "maid_offhours", "Value": "off=(m-f,19);on=(m-f,7);tz=at"}
                ]
            )
            self.assertEqual(OnHour({})(i), True)

            i = instance(
                Tags=[
                    {"Key": "maid_offhours", "Value": "off=(m-f,20);on=(m-f,6);tz=ast"}
                ]
            )
            self.assertEqual(OnHour({})(i), False)

    def test_custom_bad_tz(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=5, day=26, hour=7, minute=00)
        with mock_datetime_now(t, datetime):
            i = instance(
                Tags=[
                    {"Key": "maid_offhours", "Value": "off=(m-f,19);on=(m-f,7);tz=et"}
                ]
            )
            self.assertEqual(OnHour({})(i), True)

            i = instance(
                Tags=[
                    {"Key": "maid_offhours", "Value": "off=(m-f,20);on=(m-f,7);tz=abc"}
                ]
            )
            self.assertEqual(OnHour({})(i), False)

    def test_custom_bad_hours(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=5, day=26, hour=19, minute=00)
        # default error handling is to exclude the resource

        with mock_datetime_now(t, datetime):
            # This isn't considered a bad value, its basically omitted.
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "off=();tz=et"}])
            self.assertEqual(OffHour({})(i), False)

            i = instance(
                Tags=[
                    {"Key": "maid_offhours", "Value": "off=(m-f,90);on=(m-f,7);tz=et"}
                ]
            )
            # malformed value
            self.assertEqual(OffHour({})(i), False)

        t = t.replace(year=2016, month=5, day=26, hour=13, minute=00)
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "off=();tz=et"}])
            # will go to default values, but not work due to default time
            self.assertEqual(OffHour({})(i), False)

            i = instance(
                Tags=[
                    {"Key": "maid_offhours", "Value": "off=(m-f,90);on=(m-f,7);tz=et"}
                ]
            )
            self.assertEqual(OffHour({})(i), False)

    def test_tz_only(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=5, day=26, hour=7, minute=00)
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
            self.assertEqual(OnHour({})(i), True)

    def test_tz_long_form_resolve(self):
        pacific = zoneinfo.gettz("America/Los_Angeles")
        nzt = zoneinfo.gettz("Pacific/Auckland")
        gmt = zoneinfo.gettz("Etc/GMT")
        easter_island = zoneinfo.gettz("Chile/EasterIsland")
        self.assertEqual(
            OnHour({}).get_tz('america/los_angeles'),
            pacific)
        self.assertEqual(
            OnHour({}).get_tz('pst'),
            pacific)
        self.assertEqual(
            OnHour({}).get_tz('pacific/auckland'),
            nzt)
        self.assertEqual(
            OnHour({}).get_tz('gmt'),
            gmt)
        self.assertEqual(
            OnHour({}).get_tz('chile/easterisland'),
            easter_island)

    def test_empty_tag(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=5, day=26, hour=7, minute=00)
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": ""}])
            self.assertEqual(OnHour({})(i), True)

    def test_on_tag(self):
        t = datetime.datetime.now(zoneinfo.gettz("America/New_York"))
        t = t.replace(year=2016, month=5, day=26, hour=7, minute=00)
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "on"}])
            self.assertEqual(OnHour({})(i), True)


class ScheduleParserTest(BaseTest):
    # table style test
    # list of (tag value, parse result)
    table = [
        ################
        # Standard cases
        (
            "off=(m-f,10);on=(m-f,7);tz=et",
            {
                "off": [{"days": [0, 1, 2, 3, 4], "hour": 10}],
                "on": [{"days": [0, 1, 2, 3, 4], "hour": 7}],
                "tz": "et",
            },
        ),
        (
            "off=[(m-f,9)];on=(m-s,10);tz=pt",
            {
                "off": [{"days": [0, 1, 2, 3, 4], "hour": 9}],
                "on": [{"days": [0, 1, 2, 3, 4, 5], "hour": 10}],
                "tz": "pt",
            },
        ),
        (
            "off=[(m-f,23)];on=(m-s,10);tz=pt",
            {
                "off": [{"days": [0, 1, 2, 3, 4], "hour": 23}],
                "on": [{"days": [0, 1, 2, 3, 4, 5], "hour": 10}],
                "tz": "pt",
            },
        ),
        (
            "off=(m-f,19);on=(m-f,7);tz=pst",
            {
                "off": [{"days": [0, 1, 2, 3, 4], "hour": 19}],
                "on": [{"days": [0, 1, 2, 3, 4], "hour": 7}],
                "tz": "pst",
            },
        ),
        # wrap around days (saturday, sunday, monday)
        (
            "on=[(s-m,10)];off=(s-m,19)",
            {
                "on": [{"days": [5, 6, 0], "hour": 10}],
                "off": [{"days": [5, 6, 0], "hour": 19}],
                "tz": "et",
            },
        ),
        # multiple single days specified
        (
            "on=[(m,9),(t,10),(w,7)];off=(m-u,19)",
            {
                "on": [
                    {"days": [0], "hour": 9},
                    {"days": [1], "hour": 10},
                    {"days": [2], "hour": 7},
                ],
                "off": [{"days": [0, 1, 2, 3, 4, 5, 6], "hour": 19}],
                "tz": "et",
            },
        ),
        # using brackets also works, if only single time set
        (
            "off=[m-f,20];on=[m-f,5];tz=est",
            {
                "on": [{"days": [0, 1, 2, 3, 4], "hour": 5}],
                "off": [{"days": [0, 1, 2, 3, 4], "hour": 20}],
                "tz": "est",
            },
        ),
        # same string, exercise cache lookup.
        (
            "off=[m-f,20];on=[m-f,5];tz=est",
            {
                "on": [{"days": [0, 1, 2, 3, 4], "hour": 5}],
                "off": [{"days": [0, 1, 2, 3, 4], "hour": 20}],
                "tz": "est",
            },
        ),
        ################
        # Invalid Cases
        ("", None),
        # invalid day
        ("off=(1-2,12);on=(m-f,10);tz=est", None),
        # invalid hour
        ("off=(m-f,a);on=(m-f,10);tz=est", None),
        ("off=(m-f,99);on=(m-f,7);tz=pst", None),
        # invalid day
        ("off=(x-f,10);on=(m-f,10);tz=est", None),
        # no hour specified for on
        ("off=(m-f);on=(m-f,10);tz=est", None),
        # invalid day spec
        ("off=(m-t-f,12);on=(m-f,10);tz=est", None),
        # random extra
        ("off=(m-f,5);zebra=blue,on=(t-w,5)", None),
        ("off=(m-f,5);zebra=blue;on=(t-w,5)", None),
        # random extra again
        ("off=(m-f,5);zebrablue,on=(t-w,5)", None),
        ("bar;off=(m-f,5);zebrablue,on=(t-w,5)", None),
    ]

    def test_schedule_parser(self):
        self.maxDiff = None
        parser = ScheduleParser({"tz": "et"})
        for value, expected in self.table:
            self.assertEqual(parser.parse(value), expected)

    def test_offhours_skip(self):
        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=19,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
            self.assertEqual(OffHour({})(i), True)
            self.assertEqual(OffHour({"skip-days": ["2015-12-01"]})(i), False)
            self.assertEqual(
                OffHour({"skip-days": ["2017-01-01", "2015-12-01"]})(i), False
            )
            self.assertEqual(OffHour({"skip-days": ["2015-12-02"]})(i), True)

    def test_onhour_skip(self):
        t = datetime.datetime(
            year=2015,
            month=12,
            day=1,
            hour=7,
            minute=5,
            tzinfo=zoneinfo.gettz("America/New_York"),
        )
        with mock_datetime_now(t, datetime):
            i = instance(Tags=[{"Key": "maid_offhours", "Value": "tz=est"}])
            self.assertEqual(OnHour({})(i), True)
            self.assertEqual(OnHour({"onhour": 8})(i), False)
            self.assertEqual(OnHour({"skip-days": ["2015-12-01"]})(i), False)
            self.assertEqual(
                OnHour({"skip-days": ["2017-01-01", "2015-12-01"]})(i), False
            )
            self.assertEqual(OnHour({"skip-days": ["2015-12-02"]})(i), True)
