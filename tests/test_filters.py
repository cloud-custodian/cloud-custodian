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

import calendar
from datetime import datetime, timedelta
from dateutil import tz
from dateutil.parser import parse as parse_date
import unittest

from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n import filters as base_filters
from c7n.resources.ec2 import filters
from c7n.resources.elb import ELB
from c7n.utils import annotation
from .common import instance, event_data, Bag, BaseTest
from c7n.filters.core import ValueRegex


class BaseFilterTest(unittest.TestCase):

    def assertFilter(self, f, i, v):
        """
        f: filter data/spec
        i: instance
        v: expected value (true/false)
        """
        try:
            self.assertEqual(filters.factory(f)(i), v)
        except AssertionError:
            print(f, i["LaunchTime"], i["Tags"], v)
            raise


class TestFilter(unittest.TestCase):

    def test_filter_construction(self):
        self.assertTrue(
            isinstance(filters.factory({"tag:ASV": "absent"}), base_filters.ValueFilter)
        )

    def test_filter_validation(self):
        self.assertRaises(
            PolicyValidationError,
            filters.factory,
            {"type": "ax", "xyz": 1},
        )

    def test_filter_call(self):
        filter_instance = base_filters.Filter({})
        self.assertIsInstance(filter_instance, base_filters.Filter)


class TestOrFilter(unittest.TestCase):

    def test_or(self):
        f = filters.factory(
            {"or": [{"Architecture": "x86_64"}, {"Architecture": "armv8"}]}
        )
        results = [instance(Architecture="x86_64")]
        self.assertEqual(f.process(results), results)
        self.assertEqual(f.process([instance(Architecture="amd64")]), [])


class TestAndFilter(unittest.TestCase):

    def test_and(self):
        f = filters.factory({"and": [{"Architecture": "x86_64"}, {"Color": "green"}]})
        results = [instance(Architecture="x86_64", Color="green")]
        self.assertEqual(f.process(results), results)
        self.assertEqual(f.process([instance(Architecture="x86_64", Color="blue")]), [])
        self.assertEqual(f.process([instance(Architecture="x86_64")]), [])


class TestNotFilter(unittest.TestCase):

    def test_not(self):

        results = [
            instance(Architecture="x86_64", Color="green"),
            instance(Architecture="x86_64", Color="blue"),
            instance(Architecture="x86_64", Color="yellow"),
        ]

        f = filters.factory({"not": [{"Architecture": "x86_64"}, {"Color": "green"}]})
        self.assertEqual(len(f.process(results)), 2)

    def test_not_break_empty_set(self):
        results = [
            instance(Architecture="x86_64", Color="green")]

        f = filters.factory({"not": [{"Architecture": "amd64"}]})

        class Manager(object):

            class resource_type(object):
                id = 'Color'

            @classmethod
            def get_model(cls):
                return cls.resource_type

        class FakeFilter(object):

            def __init__(self):
                self.invoked = False

            def process(self, resources, event=None):
                self.invoked = True
                return resources

        fake = FakeFilter()
        f.filters.append(fake)
        f.manager = Manager()
        self.assertEqual(len(f.process(results)), 1)
        self.assertFalse(fake.invoked)


class TestValueFilter(unittest.TestCase):

    # TODO test_manager needs a valid session_factory object
    # def test_value_match(self):
    #     test_manager = ???
    #     f_data = {
    #         'type': 'value',
    #         'key': 'day',
    #         'value': 5,
    #         'value_from': {
    #             'url': 's3://custodian-byebye/resource.json',
    #         },
    #     }
    #     vf = filters.factory(f_data, test_manager)
    #     vf.match({'tag:ASV': 'present'})

    def test_value_type(self):
        sentinel = datetime.now()
        value = 5
        resource = {"a": 1, "Tags": [{"Key": "xtra", "Value": "hello"}]}
        vf = filters.factory({"tag:ASV": "absent"})
        vf.vtype = "size"
        res = vf.process_value_type(sentinel, value, resource)
        self.assertEqual(res, (sentinel, 0))
        vf.vtype = "cidr"
        sentinel = "10.0.0.0/16"
        value = "10.10.10.10"
        res = vf.process_value_type(sentinel, value, resource)
        self.assertEqual((str(res[0]), str(res[1])), (sentinel, value))
        vf.vtype = "cidr_size"
        value = "10.10.10.300"
        res = vf.process_value_type(sentinel, value, resource)
        self.assertEqual(res, (sentinel, 0))

        vf.vtype = "expr"
        value = None
        sentinel = "tag:xtra"
        res = vf.process_value_type(sentinel, value, resource)
        self.assertEqual(res, ("hello", None))

        vf.vtype = "expr"
        value = None
        sentinel = "a"
        res = vf.process_value_type(sentinel, value, resource)
        self.assertEqual(res, (1, None))

        vf.vtype = "unique_size"
        value = [1, 2, 3, 1, 5]
        sentinel = None
        res = vf.process_value_type(sentinel, value, resource)
        self.assertEqual(res, (None, 4))

    def test_value_type_expr(self):
        resource = {'a': 1, 'b': 1}
        vf = filters.factory({
            "type": "value",
            "value": "b",
            "op": 'eq',
            "value_type": "expr",
            "key": "a"})
        self.assertTrue(vf.match(resource))

    def test_value_match(self):
        resource = {"a": 1, "Tags": [{"Key": "xtra", "Value": "hello"}]}
        vf = filters.factory({"type": "value", "value": None, "key": "tag:xtra"})
        self.assertFalse(hasattr(vf, "content_initialized"))
        self.assertEqual(vf.v, None)

        res = vf.match(resource)

        self.assertTrue(vf.content_initialized)
        self.assertEqual(vf.v, None)
        self.assertFalse(res)


class TestAgeFilter(unittest.TestCase):

    def test_age_filter(self):
        af = base_filters.AgeFilter({})
        self.assertRaises(NotImplementedError, af.validate)


class TestGlobValue(unittest.TestCase):

    def test_regex_match(self):
        f = filters.factory(
            {"type": "value", "key": "Color", "value": "*green*", "op": "glob"}
        )
        self.assertEqual(
            f(instance(Architecture="x86_64", Color="mighty green papaya")), True
        )
        self.assertEqual(f(instance(Architecture="x86_64", Color="blue")), False)

    def test_glob_match(self):
        glob_match = base_filters.core.glob_match
        self.assertFalse(glob_match(0, ""))


class TestRegexValue(unittest.TestCase):

    def test_regex_validate(self):
        self.assertRaises(
            PolicyValidationError,
            filters.factory(
                {"type": "value", "key": "Color", "value": "*green", "op": "regex"}
            ).validate,
        )

    def test_regex_match(self):
        f = filters.factory(
            {"type": "value", "key": "Color", "value": ".*green.*", "op": "regex"}
        )
        self.assertEqual(f(instance(Architecture="x86_64", Color="green papaya")), True)
        self.assertEqual(f(instance(Architecture="x86_64", Color="blue")), False)

        self.assertEqual(f(instance(Architecture="x86_64")), False)


class TestRegexCaseSensitiveValue(unittest.TestCase):

    def test_regex_case_sensitive_validate(self):
        self.assertRaises(
            PolicyValidationError,
            filters.factory(
                {"type": "value", "key": "Color", "value": "*green", "op": "regex-case"}
            ).validate,
        )

    def test_regex_case_sensitive_match(self):
        f = filters.factory(
            {"type": "value", "key": "Color", "value": ".*GREEN.*", "op": "regex-case"}
        )
        self.assertEqual(f(instance(Architecture="x86_64", Color="GREEN papaya")), True)
        self.assertEqual(f(instance(Architecture="x86_64", Color="green papaya")), False)

        self.assertEqual(f(instance(Architecture="x86_64")), False)


class TestValueTypes(BaseFilterTest):

    def test_normalize(self):
        fdata = {
            "type": "value",
            "key": "tag:Name",
            "value_type": "normalize",
            "value": "compilelambda",
        }
        self.assertFilter(fdata, instance(), True)

    def test_size(self):
        fdata = {
            "type": "value",
            "key": "SecurityGroups[].GroupId",
            "value_type": "size",
            "value": 2,
        }
        self.assertFilter(fdata, instance(), True)

    def test_integer(self):
        fdata = {
            "type": "value",
            "key": "tag:Count",
            "op": "greater-than",
            "value_type": "integer",
            "value": 0,
        }

        def i(d):
            return instance(Tags=[{"Key": "Count", "Value": d}])

        self.assertFilter(fdata, i("42"), True)
        self.assertFilter(fdata, i("abc"), False)

        fdata["op"] = "equal"
        self.assertFilter(fdata, i("abc"), True)

    def test_integer_with_value_regex(self):
        fdata = {
            "type": "value",
            "key": "tag:Count",
            "op": "greater-than",
            "value_regex": r".*data=([0-9]+)",
            "value_type": "integer",
            "value": 0,
        }

        def i(d):
            value = "mode=5;data={}".format(d)
            return instance(Tags=[{"Key": "Count", "Value": value}])

        self.assertFilter(fdata, i("42"), True)
        self.assertFilter(fdata, i("0"), False)
        self.assertFilter(fdata, i("abc"), False)

        fdata["op"] = "equal"
        self.assertFilter(fdata, i("42"), False)
        self.assertFilter(fdata, i("0"), True)
        # This passes because the 'integer' value_type
        # returns '0' when it fails to parse an int.
        # Making abc == 0 evaluate to True seems dangerous,
        # but it's existing behaviour.
        self.assertFilter(fdata, i("abc"), True)

    def test_swap(self):
        fdata = {
            "type": "value",
            "key": "SecurityGroups[].GroupId",
            "value_type": "swap",
            "op": "in",
            "value": "sg-47b76f22",
        }
        self.assertFilter(fdata, instance(), True)

    def test_age(self):
        now = datetime.now(tz=tz.tzutc())
        three_months = now - timedelta(90)
        two_months = now - timedelta(60)
        one_month = now - timedelta(30)

        def i(d):
            return instance(LaunchTime=d)

        fdata = {
            "type": "value",
            "key": "LaunchTime",
            "op": "less-than",
            "value_type": "age",
            "value": 32,
        }

        self.assertFilter(fdata, i(three_months), False)
        self.assertFilter(fdata, i(two_months), False)
        self.assertFilter(fdata, i(one_month), True)
        self.assertFilter(fdata, i(now), True)
        self.assertFilter(fdata, i(now.isoformat()), True)
        self.assertFilter(fdata, i(now.isoformat()), True)
        self.assertFilter(fdata, i(calendar.timegm(now.timetuple())), True)
        self.assertFilter(fdata, i(str(calendar.timegm(now.timetuple()))), True)

    def test_date(self):
        def i(d):
            return instance(LaunchTime=d)

        fdata = {
            'type': 'value',
            'key': 'LaunchTime',
            'op': 'less-than',
            'value_type': 'date',
            'value': '2019/05/01'}

        self.assertFilter(fdata, i(parse_date('2019/04/01')), True)
        self.assertFilter(fdata, i(datetime.now().isoformat()), False)

    def test_version(self):
        fdata = {
            "type": "value",
            "key": "Version",
            "op": "less-than",
            "value_type": "version",
            "value": "1.9.12",
        }

        def i(v):
            return instance(Version=v)

        self.assertFilter(fdata, i("1.32.1"), False)
        self.assertFilter(fdata, i("1.9.13"), False)
        self.assertFilter(fdata, i("1.9.11"), True)
        self.assertFilter(fdata, i("1.1"), True)

    def test_expiration(self):

        now = datetime.now(tz=tz.tzutc())
        three_months = now + timedelta(90)
        two_months = now + timedelta(60)

        def i(d):
            return instance(LaunchTime=d)

        fdata = {
            "type": "value",
            "key": "LaunchTime",
            "op": "less-than",
            "value_type": "expiration",
            "value": 61,
        }

        self.assertFilter(fdata, i(three_months), False)
        self.assertFilter(fdata, i(two_months), True)
        self.assertFilter(fdata, i(now), True)
        self.assertFilter(fdata, i(now.isoformat()), True)

    def test_expiration_with_value_regex(self):

        now = datetime.now(tz=tz.tzutc())
        three_months = now + timedelta(90)
        two_months = now + timedelta(60)

        def i(c, e):
            value = "creation={};expiry={}".format(c, e)
            return instance(Tags=[{"Key": "metadata", "Value": value}])

        fdata = {
            "type": "value",
            "key": "tag:metadata",
            "op": "less-than",
            "value_regex": r".*expiry=([0-9-:\s\+\.T]+Z?)",
            "value_type": "expiration",
            "value": 61,
        }

        self.assertFilter(fdata, i((three_months - timedelta(100)), three_months), False)
        self.assertFilter(fdata, i((two_months - timedelta(100)), two_months), True)
        self.assertFilter(fdata, i((now - timedelta(100)), now), True)
        self.assertFilter(fdata, i((now - timedelta(100)).isoformat(), now.isoformat()), True)

    def test_value_regex_matches_first_occurrence(self):

        def i(first, second):
            value = "{}text{}".format(first, second)
            return instance(Tags=[{"Key": "metadata", "Value": value}])

        fdata = {
            "type": "value",
            "key": "tag:metadata",
            "op": "equal",
            "value_regex": r"([0-9])",
            "value_type": "integer",
            "value": 3,
        }

        self.assertFilter(fdata, i(2, 3), False)
        self.assertFilter(fdata, i(3, 2), True)

        fdata['value_regex'] = r".*([0-9])"
        self.assertFilter(fdata, i(2, 3), True)
        self.assertFilter(fdata, i(3, 2), False)

    def test_value_regex_with_non_capturing_groups(self):

        def i(d):
            return instance(Tags=[{"Key": "metadata", "Value": d}])

        fdata = {
            "type": "value",
            "key": "tag:metadata",
            "op": "equal",
            "value_regex": r"(?:oldformat|newformat)=(expected\s\w+)",
            "value_type": "string",
            "value": "expected value",
        }

        self.assertFilter(fdata, i("newformat=expected value"), True)
        self.assertFilter(fdata, i("oldformat=expected value"), True)
        self.assertFilter(fdata, i("otherformat=expected value"), False)

    def test_value_regex_validation(self):
        # Regex won't compile
        fdata = {
            "type": "value",
            "key": "tag:metadata",
            "op": "less-than",
            "value_regex": r".*expiry=?????[([0-9)",
            "value_type": "expiration",
            "value": 61,
        }
        self.assertRaises(PolicyValidationError, filters.factory(fdata, {}).validate)

        # More than one capture group
        fdata = {
            "type": "value",
            "key": "tag:metadata",
            "op": "less-than",
            "value_regex": r".*(expiry)=([0-9-:\s\+\.T]+Z?)",
            "value_type": "expiration",
            "value": 61,
        }
        self.assertRaises(PolicyValidationError, filters.factory(fdata, {}).validate)

        # No capture group
        fdata = {
            "type": "value",
            "key": "tag:metadata",
            "op": "less-than",
            "value_regex": r".*expiry=[0-9-:\s\+\.T]+Z?",
            "value_type": "expiration",
            "value": 61,
        }
        self.assertRaises(PolicyValidationError, filters.factory(fdata, {}).validate)

        # One capture group and non-capturing groups (should not error)
        fdata = {
            "type": "value",
            "key": "tag:metadata",
            "op": "less-than",
            "value_regex": r"pet=(?:cat|dog);number=([0-9]{1,4})",
            "value_type": "integer",
            "value": 12,
        }
        filters.factory(fdata, {}).validate

    def test_value_regex_match(self):
        fdata = {
            "type": "value",
            "key": "tag:metadata",
            "op": "less-than",
            "value_regex": r"pet=(?:cat|dog);number=([0-9]{1,4})",
            "value_type": "integer",
            "value": 12,
        }
        capture = ValueRegex(fdata['value_regex'])

        # No match returns None
        retValue = capture.get_resource_value("pet=elephant;number=3")
        self.assertIsNone(retValue)
        # TypeError returns None
        retValue = capture.get_resource_value(True)
        self.assertIsNone(retValue)
        # Match returns matched value
        retValue = capture.get_resource_value("pet=dog;number=44")
        self.assertEqual("44", retValue)

    def test_resource_count_filter(self):
        fdata = {
            "type": "value", "value_type": "resource_count", "op": "lt", "value": 2
        }
        self.assertFilter(fdata, instance(file="ec2-instances.json"), [])

        f = filters.factory(
            {"type": "value", "value_type": "resource_count", "op": "eq", "value": 2}
        )
        i = instance(file="ec2-instances.json")
        self.assertEqual(i, f(i))

    def test_resource_count_filter_validation(self):
        # Bad `op`
        f = {"type": "value", "value_type": "resource_count", "op": "regex", "value": 1}
        self.assertRaises(
            PolicyValidationError, filters.factory(f, {}).validate
        )

        # Bad `value`
        f = {
            "type": "value", "value_type": "resource_count", "op": "eq", "value": "foo"
        }
        self.assertRaises(
            PolicyValidationError, filters.factory(f, {}).validate
        )

        # Missing `op`
        f = {"type": "value", "value_type": "resource_count", "value": 1}
        self.assertRaises(
            PolicyValidationError, filters.factory(f, {}).validate
        )

        # Unexpected `value_regex`
        f = {
            "type": "value", "value_type": "resource_count", "op": "eq", "value": "foo",
            "value_regex": "([0-7]{3,7})"
        }
        self.assertRaises(
            PolicyValidationError, filters.factory(f, {}).validate
        )


class TestInstanceAge(BaseFilterTest):

    def test_filter_instance_age(self):
        now = datetime.now(tz=tz.tzutc())
        three_months = now - timedelta(90)
        two_months = now - timedelta(60)
        one_month = now - timedelta(30)

        def i(d):
            return instance(LaunchTime=d)

        for ii, v in [
            (i(now), False),
            (i(three_months), True),
            (i(two_months), True),
            (i(one_month), False),
        ]:
            self.assertFilter(
                {"type": "instance-uptime", "op": "gte", "days": 60}, ii, v
            )


class TestInstanceAgeMinute(BaseFilterTest):

    def test_filter_instance_age(self):
        now = datetime.now(tz=tz.tzutc())
        five_minute = now - timedelta(minutes=5)

        def i(d):
            return instance(LaunchTime=d)

        for ii, v in [(i(now), False), (i(five_minute), True)]:
            self.assertFilter(
                {"type": "instance-uptime", "op": "gte", "minutes": 5}, ii, v
            )


class TestMarkedForAction(BaseFilterTest):

    def test_marked_for_op_with_skew(self):
        now = datetime.now()
        yesterday = datetime.now() - timedelta(7)
        next_week = now + timedelta(7)

        def i(d, action="stop"):
            return instance(
                Tags=[
                    {
                        "Key": "maid_status",
                        "Value": "not compliant: %s@%s"
                        % (action, d.strftime("%Y/%m/%d")),
                    }
                ]
            )

        for inst, skew, expected in [
            (i(next_week), 7, True),
            (i(next_week), 3, False),
            (i(now), 0, True),
            (i(now), 5, True),
            (i(yesterday), 5, True),
            (i(now + timedelta(1)), 1, True),
            (i(now + timedelta(2)), 1, False),
            (i(now + timedelta(3)), 1, False),
        ]:
            self.assertFilter({"type": "marked-for-op", "skew": skew}, inst, expected)

    def test_filter_action_date(self):
        now = datetime.now()
        yesterday = now - timedelta(1)
        tomorrow = now + timedelta(1)

        def i(d, action="stop"):
            return instance(
                Tags=[
                    {
                        "Key": "maid_status",
                        "Value": "not compliant: %s@%s"
                        % (action, d.strftime("%Y/%m/%d")),
                    }
                ]
            )

        for ii, v in [
            (i(yesterday), True),
            (i(now), True),
            (i(tomorrow), False),
            (i(yesterday, "terminate"), False),
        ]:
            self.assertFilter({"type": "marked-for-op"}, ii, v)


class EventFilterTest(BaseFilterTest):

    def test_event_filter(self):
        b = Bag(data={"mode": []})
        event = event_data("event-instance-state.json")
        f = {"type": "event", "key": "detail.state", "value": "pending"}
        ef = filters.factory(f, b)
        self.assertTrue(ef.process([instance()], event))
        # event is None
        self.assertEqual(ef.process("resources"), "resources")
        # event is not None, but is not "true" either
        self.assertEqual(ef.process("resources", []), [])

    def test_event_no_mode(self):
        b = Bag(data={"resource": "something"})
        f = {"type": "event", "key": "detail.state", "value": "pending"}
        f = filters.factory(f, b)
        self.assertRaises(PolicyValidationError, f.validate)


class TestInstanceValue(BaseFilterTest):

    def test_filter_tag_count(self):
        tags = []
        for i in range(10):
            tags.append({"Key": str(i), "Value": str(i)})
        i = instance(Tags=tags)
        self.assertFilter({"type": "tag-count", "op": "lt"}, i, False)
        tags.pop(0)
        i = instance(Tags=tags)
        self.assertFilter({"type": "tag-count", "op": "gte", "count": 9}, i, True)

    def test_filter_tag(self):
        i = instance(Tags=[{"Key": "ASV", "Value": "abcd"}])
        self.assertFilter({"tag:ASV": "def"}, i, False)
        self.assertEqual(annotation(i, base_filters.ANNOTATION_KEY), ())

        i = instance(Tags=[{"Key": "CMDB", "Value": "abcd"}])
        self.assertFilter({"tag:ASV": "absent"}, i, True)
        self.assertEqual(annotation(i, base_filters.ANNOTATION_KEY), ["tag:ASV"])

    def test_present(self):
        i = instance(Tags=[{"Key": "ASV", "Value": ""}])
        self.assertFilter(
            {"type": "value", "key": "tag:ASV", "value": "present"}, i, True
        )

    def test_jmespath(self):
        self.assertFilter(
            {"Placement.AvailabilityZone": "us-west-2c"}, instance(), True
        )

        self.assertFilter(
            {"Placement.AvailabilityZone": "us-east-1c"}, instance(), False
        )

    def test_complex_validator(self):
        self.assertRaises(
            PolicyValidationError,
            filters.factory({"key": "xyz", "type": "value"}).validate,
        )
        self.assertRaises(
            PolicyValidationError,
            filters.factory({"value": "xyz", "type": "value"}).validate,
        )

        self.assertRaises(
            PolicyValidationError,
            filters.factory(
                {"key": "xyz", "value": "xyz", "op": "oo", "type": "value"}
            ).validate,
        )

    def test_complex_value_filter(self):
        self.assertFilter(
            {
                "key": (
                    "length(BlockDeviceMappings"
                    "[?Ebs.DeleteOnTermination == `true`]"
                    ".Ebs.DeleteOnTermination)"
                ),
                "value": 0,
                "type": "value",
                "op": "gt",
            },
            instance(),
            True,
        )

    def test_not_null_filter(self):
        self.assertFilter(
            {"key": "Hypervisor", "value": "not-null", "type": "value"},
            instance(),
            True,
        )


class TestEqualValue(unittest.TestCase):

    def test_eq(self):
        f = filters.factory(
            {"type": "value", "key": "Color", "value": "green", "op": "eq"}
        )
        self.assertEqual(f(instance(Color="green")), True)
        self.assertEqual(f(instance(Color="blue")), False)

    def test_equal(self):
        f = filters.factory(
            {"type": "value", "key": "Color", "value": "green", "op": "equal"}
        )
        self.assertEqual(f(instance(Color="green")), True)
        self.assertEqual(f(instance(Color="blue")), False)


class TestNotEqualValue(unittest.TestCase):

    def test_ne(self):
        f = filters.factory(
            {"type": "value", "key": "Color", "value": "green", "op": "ne"}
        )
        self.assertEqual(f(instance(Color="green")), False)
        self.assertEqual(f(instance(Color="blue")), True)

    def test_not_equal(self):
        f = filters.factory(
            {"type": "value", "key": "Color", "value": "green", "op": "not-equal"}
        )
        self.assertEqual(f(instance(Color="green")), False)
        self.assertEqual(f(instance(Color="blue")), True)


class TestGreaterThanValue(unittest.TestCase):

    def test_gt(self):
        f = filters.factory({"type": "value", "key": "Number", "value": 10, "op": "gt"})
        self.assertEqual(f(instance(Number=11)), True)
        self.assertEqual(f(instance(Number=9)), False)
        self.assertEqual(f(instance(Number=10)), False)

    def test_greater_than(self):
        f = filters.factory(
            {"type": "value", "key": "Number", "value": 10, "op": "greater-than"}
        )
        self.assertEqual(f(instance(Number=11)), True)
        self.assertEqual(f(instance(Number=9)), False)
        self.assertEqual(f(instance(Number=10)), False)


class TestLessThanValue(unittest.TestCase):

    def test_lt(self):
        f = filters.factory({"type": "value", "key": "Number", "value": 10, "op": "lt"})
        self.assertEqual(f(instance(Number=9)), True)
        self.assertEqual(f(instance(Number=11)), False)
        self.assertEqual(f(instance(Number=10)), False)

    def test_less_than(self):
        f = filters.factory(
            {"type": "value", "key": "Number", "value": 10, "op": "less-than"}
        )
        self.assertEqual(f(instance(Number=9)), True)
        self.assertEqual(f(instance(Number=11)), False)
        self.assertEqual(f(instance(Number=10)), False)


class TestInList(unittest.TestCase):

    def test_in(self):
        f = filters.factory(
            {
                "type": "value",
                "key": "Thing",
                "value": ["Foo", "Bar", "Quux"],
                "op": "in",
            }
        )
        self.assertEqual(f(instance(Thing="Foo")), True)
        self.assertEqual(f(instance(Thing="Baz")), False)


class TestNotInList(unittest.TestCase):

    def test_ni(self):
        f = filters.factory(
            {
                "type": "value",
                "key": "Thing",
                "value": ["Foo", "Bar", "Quux"],
                "op": "ni",
            }
        )
        self.assertEqual(f(instance(Thing="Baz")), True)
        self.assertEqual(f(instance(Thing="Foo")), False)

    def test_not_in(self):
        f = filters.factory(
            {
                "type": "value",
                "key": "Thing",
                "value": ["Foo", "Bar", "Quux"],
                "op": "not-in",
            }
        )
        self.assertEqual(f(instance(Thing="Baz")), True)
        self.assertEqual(f(instance(Thing="Foo")), False)


class TestContains(unittest.TestCase):

    def test_contains(self):
        f = filters.factory(
            {"type": "value", "key": "Thing", "value": "D", "op": "contains"}
        )
        self.assertEqual(f(instance(Thing=["A", "B", "C"])), False)
        self.assertEqual(f(instance(Thing=["D", "E", "F"])), True)


class TestDifference(unittest.TestCase):

    def test_difference(self):
        f = filters.factory(
            {
                "type": "value",
                "key": "Thing",
                "value": ["A", "B", "C"],
                "op": "difference",
            }
        )
        self.assertEqual(f(instance(Thing=["A", "B", "C"])), False)
        self.assertEqual(f(instance(Thing=["D", "E", "F"])), True)
        self.assertEqual(f(instance(Thing=["A", "B", "D"])), True)


class TestIntersect(unittest.TestCase):

    def test_intersect(self):
        f = filters.factory(
            {
                "type": "value",
                "key": "Thing",
                "value": ["A", "B", "C"],
                "op": "intersect",
            }
        )
        self.assertEqual(f(instance(Thing=["D", "E", "F"])), False)
        self.assertEqual(f(instance(Thing=["C", "D", "E"])), True)


class TestFilterRegistry(unittest.TestCase):

    def test_filter_registry(self):
        reg = base_filters.FilterRegistry("test.filters")
        self.assertRaises(PolicyValidationError, reg.factory, {"type": ""})


class TestMissingMetrics(BaseTest):

    def test_missing_metrics(self):
        self.patch(ELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_missing_metrics")

        p = self.load_policy(
            {
                "name": "elb-missing-metrics",
                "resource": "elb",
                "filters": [
                    {
                        "type": "metrics",
                        "value": 0,
                        "name": "RequestCount",
                        "op": "eq",
                        "statistics": "Sum",
                    }
                ],
            },
            config={"account_id": "644160558196"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_missing_metrics_with_fillvalue(self):
        self.patch(ELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_missing_metrics")

        p = self.load_policy(
            {
                "name": "elb-missing-metrics-with-fill",
                "resource": "elb",
                "filters": [
                    {
                        "type": "metrics",
                        "value": 0,
                        "name": "RequestCount",
                        "op": "eq",
                        "statistics": "Sum",
                        "missing-value": 0.0,
                    }
                ],
            },
            config={"account_id": "644160558196"},
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 2)
        self.assertEqual(all(
            isinstance(res["c7n.metrics"]["AWS/ELB.RequestCount.Sum"], list)
            for res in resources
        ), True)
        self.assertIn(
            "Fill value for missing data",
            (res["c7n.metrics"]["AWS/ELB.RequestCount.Sum"][0].get("c7n:detail")
                for res in resources)
        )


if __name__ == "__main__":
    unittest.main()
