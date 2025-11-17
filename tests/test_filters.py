# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
import copy
import calendar
from collections import namedtuple
from datetime import datetime, timedelta
from dateutil import tz
from dateutil.parser import parse as parse_date
import logging
import random
import unittest
import os

from c7n.exceptions import PolicyValidationError, PolicyExecutionError
from c7n.executor import MainThreadExecutor
from c7n import filters as base_filters
from c7n.resources.ec2 import filters
from c7n.resources.elb import ELB
from c7n.testing import mock_datetime_now
from c7n.utils import annotation
from .common import instance, event_data, Bag, BaseTest
from c7n.filters.core import AnnotationSweeper, ValueRegex, parse_date as core_parse_date


class BaseFilterTest(BaseTest):

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

    def test_merge_annotation(self):
        filter_instance1 = base_filters.Filter({})
        filter_instance2 = base_filters.Filter({})
        filter_instance1.matched_annotation_key = 'c7n:matched-keys'
        filter_instance2.matched_annotation_key = 'c7n:matched-keys'
        filter_instance1.get_block_operator = lambda: 'and'
        filter_instance2.get_block_operator = lambda: 'and'

        resource1 = {'Arn': 'arn:aws:iam::123456789012:user/zscholl',
                     'CreateDate': datetime(2020, 1, 2, 17, 53, 23, 976000, tzinfo=tz.tzutc()),
                     'Path': '/',
                     'UserId': 'xafegj4qjwfl3mpuvyj5',
                     'UserName': 'zscholl'}
        resource2 = {'Arn': 'arn:aws:iam::123456789012:user/zscholl',
                     'CreateDate': datetime(2020, 1, 2, 17, 53, 23, 976000, tzinfo=tz.tzutc()),
                     'Path': '/',
                     'UserId': 'xafegj4qjwfl3mpuvyj5',
                     'UserName': 'zscholl'}

        value1 = {'active': True, 'c7n:match-type': 'credential',
                 'last_rotated': '2019-01-04T17:53:24+00:00',
                 'last_used_date': '2019-01-04T17:53:24+00:00',
                 'last_used_region': 'not_supported',
                 'last_used_service': 'not_supported'}

        value2 = {'active': True, 'c7n:match-type': 'credential',
                 'last_rotated': '2020-01-02T18:53:24+00:00',
                 'last_used_date': '2020-01-04T17:53:24+00:00',
                 'last_used_region': 'not_supported',
                 'last_used_service': 'not_supported'}
        filter_instance1.merge_annotation(resource1, 'c7n:matched-keys', [value1, value2])
        filter_instance1.merge_annotation(resource1, 'c7n:matched-keys', [value1])

        filter_instance2.merge_annotation(resource2, 'c7n:matched-keys', [value1])
        filter_instance2.merge_annotation(resource2, 'c7n:matched-keys', [value1, value2])

        self.assertEqual(resource1, resource2)


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

        class Manager:

            class resource_type:
                id = 'Color'

            @classmethod
            def get_model(cls):
                return cls.resource_type

        class FakeFilter:

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

        # test explicit op
        vf = filters.factory({
            "type": "value",
            "value": "b",
            "op": 'eq',
            "value_type": "expr",
            "key": "a"})
        self.assertTrue(vf.match(resource))

        # test implicit/fallback op
        vf = filters.factory({
            "type": "value",
            "value": "b",
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

    def test_value_type_cidr(self):
        # test cidr range match
        resource = {"ingress": "10.10.10.0/24"}
        TestCidrValue = namedtuple("TestCidrValue", ["value", "contains_resource"])

        test_networks = [
            TestCidrValue("10.10.0.0/16", True),
            TestCidrValue(["10.10.0.0/16"], True),
            TestCidrValue(["172.17.0.0/24", "10.10.0.0/16"], True),
            TestCidrValue("10.0.0.0/16", False),
            TestCidrValue(["10.0.0.0/16"], False),
            TestCidrValue(["172.17.0.0/24", "10.0.0.0/16"], False)
        ]

        for net in test_networks:
            vf = filters.factory({
                "type": "value",
                "value": net.value,
                "op": "in",
                "value_type": "cidr",
                "key": "ingress"})
            res = vf.match(resource)
            self.assertEqual(res, net.contains_resource)

            vf = filters.factory({
                "type": "value",
                "value": net.value,
                "op": "not-in",
                "value_type": "cidr",
                "key": "ingress"})
            res = vf.match(resource)
            self.assertEqual(res, not net.contains_resource)

        resource = {"ingress": "xyz"}
        vf = filters.factory({
            "type": "value",
            "value": ["abc"],
            "op": "in",
            "value_type": "cidr",
            "key": "ingress"})
        self.assertRaises(TypeError, vf.match(resource))

    def test_value_path(self):
        resource = {'list': [{'a': ['one', 'two'], 'b': 'one'}, {'a': ['one'], 'b': 'two'}]}
        vf = filters.factory({
            "type": "value",
            "key": "list[?(b=='one')].a[]",
            "value_path": "list[?(b=='two')].a[]",
            "op": "intersect"})
        res = vf.match(resource)
        self.assertEqual(res, True)

        vf = filters.factory({
            "type": "value",
            "key": "list[?(b=='one')].a[]",
            "value_path": "list[?(b=='three')].a[]",
            "op": "intersect"})
        res = vf.match(resource)
        self.assertEqual(res, False)


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

    def test_float(self):
        fdata = {
            "type": "value",
            "key": "tag:Cost",
            "op": "greater-than",
            "value_type": "float",
            "value": 10.0,
        }

        def i(d):
            return instance(Tags=[{"Key": "Cost", "Value": d}])

        self.assertFilter(fdata, i("9.9"), False)
        self.assertFilter(fdata, i("42.1"), True)
        self.assertFilter(fdata, i("42"), True)
        self.assertFilter(fdata, i("abc"), False)

        # set default value to 0.0 if the given value is not float
        fdata["op"] = "equal"
        fdata["value"] = 0.0
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

    def test_parse_date_epoch(self):
        def t(s, y):
            dt = core_parse_date(s)
            if y is None:
                self.assertEqual(dt, None)
            else:
                self.assertEqual(dt.year, y)

        t("1234567890", 2009)       # (2009, 2, 13, 15, 31, 30)
        t("1234567890123", 2009)    # (2009, 2, 13, 15, 31, 30, 123000)

        t("12345678901", 2361)      # (2361, 3, 21, 12, 15, 1)
        t("12345678901234", 2361)   # (2361, 3, 21, 12, 15, 1, 234000)

        if os.name == "nt":
            # too big for windows
            t("123456789012", 1973)     # (1973, 11, 29, 13, 33, 9, 012000)
            t("123456789012345", None)
        else:
            t("123456789012", 5882)     # (5882, 3, 10, 16, 30, 12)
            t("123456789012345", 5882)  # (5882, 3, 10, 16, 30, 12, 345000)

        # nothing should be able to parse this
        t("1234567890123456", None)

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

    def test_normalized_keys_filter(self):
        i = instance(Tags=[{"Key": " foo", "Value": "abcd"}])
        self.assertFilter({"tag:foo": "abcd"}, i, False)
        fdata = {
            "type": "value",
            "key": "tag:foo",
            "tag_key_transforms": ["strip"],
            "value": "abcd",
        }
        self.assertFilter(fdata, i, True)
        self.assertEqual(annotation(i, base_filters.ANNOTATION_KEY), ["tag:foo"])

        fdata_with_bad_transform = {
            "type": "value",
            "key": "tag:foo",
            "tag_key_transforms": ["spam"],
            "value": "abcd",
        }
        with self.capture_logging(level=logging.WARNING) as log_output:
            self.assertFilter(fdata_with_bad_transform, i, False)
            self.assertIn("Ignoring invalid tag key transform: spam", log_output.getvalue())

        i = instance(Tags=[{"Key": " foo_bar", "Value": "abcd"}])
        self.assertFilter({"tag:FooBar": "abcd"}, i, False)
        fdata_big = {
            "type": "value",
            "key": "tag:FooBar",
            "tag_key_transforms": ["strip", "title", "nounderscores"],
            "value": "abcd",
        }
        self.assertFilter(fdata_big, i, True)
        self.assertEqual(
            annotation(i, base_filters.ANNOTATION_KEY),
            ["tag:FooBar"],
        )

        # make instance tags GCP-like by removing "Tags" and adding "labels"
        i = instance()
        del i["Tags"]
        i["labels"] = {" foo": "abcd"}
        self.assertFilter({"tag:foo": "abcd"}, i, False)
        self.assertFilter(fdata, i, True)
        self.assertEqual(annotation(i, base_filters.ANNOTATION_KEY), ["tag:foo"])


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


class TestModValue(unittest.TestCase):
    def test_mod(self):
        f = filters.factory({
            "type": "value",
            "key": "Number",
            "value": 3,
            "op": "mod"
        })
        self.assertEqual(f(instance(Number=3)), False)
        self.assertEqual(f(instance(Number=6)), False)
        self.assertEqual(f(instance(Number=24)), False)
        self.assertEqual(f(instance(Number=2)), True)
        self.assertEqual(f(instance(Number=5)), True)
        self.assertEqual(f(instance(Number=23)), True)


class TestFilterRegistry(unittest.TestCase):

    def test_filter_registry(self):
        reg = base_filters.FilterRegistry("test.filters")
        self.assertRaises(PolicyValidationError, reg.factory, {"type": ""})


class TestMetricsFilter(BaseTest):

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
            isinstance(res["c7n.metrics"]["AWS/ELB.RequestCount.Sum.14"], list)
            for res in resources
        ), True)
        self.assertIn(
            "Fill value for missing data",
            (res["c7n.metrics"]["AWS/ELB.RequestCount.Sum.14"][0].get("c7n:detail")
                for res in resources)
        )

    def test_metric_period_rounding(self):
        """Round metrics start and end times to align with CloudWatch retention periods"""

        with mock_datetime_now(parse_date("2020-12-03T04:47:15+00:00"), base_filters.metrics):
            for (days, expected_start, expected_end) in (
                ((1 / 24.0), "2020-12-03T03:47:16+00:00", "2020-12-03T04:47:16+00:00"),
                (1, "2020-12-02T04:48:00+00:00", "2020-12-03T04:48:00+00:00"),
                (20, "2020-11-13T04:50:00+00:00", "2020-12-03T04:50:00+00:00"),
                (90, "2020-09-04T05:00:00+00:00", "2020-12-03T05:00:00+00:00"),
            ):
                p = self.load_policy(
                    {
                        "name": "sqs-no-messages",
                        "resource": "sqs",
                        "filters": [
                            {
                                "type": "metrics",
                                "name": "NumberOfMessagesSent",
                                "statistics": "Sum",
                                "days": days,
                                "value": 0,
                                "op": "eq"
                            }
                        ]
                    }
                )
                metrics_filter = p.resource_manager.filters[0]
                window = metrics_filter.get_metric_window()
                self.assertEqual(parse_date(expected_start), window.start)
                self.assertEqual(parse_date(expected_end), window.end)

    def test_metric_period_too_long(self):
        """The longest CloudWatch retention period is 455 days. If we specify a period like 900
        days, CloudWatch will happily show us 455 days of data with a start date 900 days ago.
        Avoid that sort of confusion in validation."""

        with self.assertRaises(PolicyValidationError) as err:
            self.load_policy({
                "name": "sqs-metrics-period-too-long",
                "resource": "sqs",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "NumberOfMessagesSent",
                        "statistics": "Sum",
                        "days": 900,
                        "value": 0,
                        "op": "eq"
                    }
                ]
            })
        self.assertIn('cannot exceed 455', str(err.exception))


class TestReduceFilter(BaseFilterTest):

    def instances(self):
        return [
            dict(InstanceId="A", Group="A", Foo="a", Bar="3", Date="2011/05/06"),
            dict(InstanceId="B", Group="B", Foo="c", Bar="1", Date="2020/01/01"),
            dict(InstanceId="C", Group="C", Foo="d", Date="2015-05-25T01:02:03"),
            dict(InstanceId="D", Group="A", Foo="b", Date="1592870000"),  # 2020-06-22 23:53:20 UTC
            dict(InstanceId="E", Group="B", Foo="e", Bar="23", Date="invalid"),
            dict(InstanceId="F", Group="C", Foo="f"),
        ]

    def test_limit(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "limit": 2,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), 2)

    def test_limit_no_number(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "limit": 0,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), len(resources))

    def test_limit_negative_number(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "limit": -2,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), len(resources))

    def test_limit_percent(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "limit-percent": 50,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), 3)
        self.assertEqual([r['InstanceId'] for r in rs], ['A', 'B', 'C'])

    def test_limit_percent_and_count(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "limit": 2,
                "limit-percent": 50,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), 2)
        self.assertEqual([r['InstanceId'] for r in rs], ['A', 'B'])

    def test_discard(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "discard": 2,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), 4)

    def test_discard_percent(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "discard": 2,
                "discard-percent": 50,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), 3)
        self.assertEqual([r['InstanceId'] for r in rs], ['D', 'E', 'F'])

    def test_discard_and_limit(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "discard": 2,
                "limit": 2,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), 2)
        self.assertEqual([r['InstanceId'] for r in rs], ['C', 'D'])

    def test_sort(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "sort-by": "Foo",
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), len(resources))
        self.assertEqual([r['Foo'] for r in rs], ['a', 'b', 'c', 'd', 'e', 'f'])

    def test_sort_desc(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "sort-by": "Foo",
                "order": "desc",
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), len(resources))
        self.assertEqual([r['Foo'] for r in rs], ['f', 'e', 'd', 'c', 'b', 'a'])

    def test_group_sort(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "group-by": "Group",
                "sort-by": "Foo",
                "order": "desc",
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), len(resources))
        self.assertEqual([r['InstanceId'] for r in rs], ['F', 'C', 'E', 'B', 'D', 'A'])
        ['D', 'A', 'E', 'B', 'F', 'C']

    def test_group_sort_limit(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "group-by": "Group",
                "sort-by": "Foo",
                "order": "desc",
                "limit": 1,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), 3)
        self.assertEqual([r['InstanceId'] for r in rs], ['F', 'E', 'D'])

    def test_randomize(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "order": "randomize",
            }
        )
        # Set the rand seed to ensure that the random sets aren't accidentally
        # the same.
        random.seed(1234)
        rs1 = f.process(resources)
        rs2 = f.process(resources)
        self.assertEqual(len(rs1), len(resources))
        self.assertEqual(len(rs2), len(resources))
        self.assertNotEqual(
            [r['InstanceId'] for r in rs1],
            [r['InstanceId'] for r in rs2]
        )

    def test_reverse(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "order": "reverse",
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), len(resources))
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            [r['InstanceId'] for r in resources[::-1]]
        )

    def test_sort_string(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "sort-by": "Bar",
            }
        )
        rs = f.process(resources)
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            ['B', 'E', 'A', 'C', 'D', 'F']
        )

    def test_sort_number(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "sort-by": {
                    "key": "Bar",
                    "value_type": "number"
                }
            }
        )
        rs = f.process(resources)
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            ['B', 'A', 'E', 'C', 'D', 'F']
        )

    def test_sort_date(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "sort-by": {
                    "key": "Date",
                    "value_type": "date"
                }
            }
        )
        rs = f.process(resources)
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            ['A', 'C', 'B', 'D', 'E', 'F']
        )

    def test_group_string(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "group-by": "Bar",
                "limit": 1,
            }
        )
        rs = f.process(resources)
        self.assertEqual(len(rs), 4)
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            ['B', 'E', 'A', 'C']
        )

    def test_group_number(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "group-by": {
                    "key": "Bar",
                    "value_type": "number"
                },
                "limit": 1
            }
        )
        rs = f.process(resources)
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            ['B', 'A', 'E', 'C']
        )

    def test_group_regex_date_asc(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "group-by": {
                    "key": "Date",
                    "value_type": "date",
                    "value_regex": "([0-9]{4}-[0-9]{2}-[0-9]{2}).*"
                },
                "limit": 1
            }
        )
        f.validate()
        rs = f.process(resources)
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            ['C', 'A']
        )

    def test_group_regex_date_desc(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "group-by": {
                    "key": "Date",
                    "value_type": "date",
                    "value_regex": "([0-9]{4}[/-][0-9]{2}[/-][0-9]{2}).*",
                },
                "order": "desc",
                "limit": 1
            }
        )
        rs = f.process(resources)
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            ['B', 'C', 'A', 'D']
        )

    def test_group_regex_date_desc_null_first(self):
        resources = self.instances()
        f = filters.factory(
            {
                "type": "reduce",
                "group-by": {
                    "key": "Date",
                    "value_type": "date",
                    "value_regex": "([0-9]{4}[/-][0-9]{2}[/-][0-9]{2}).*",
                },
                "order": "desc",
                "null-order": "first",
                "limit": 1
            }
        )
        rs = f.process(resources)
        self.assertEqual(
            [r['InstanceId'] for r in rs],
            ['D', 'B', 'C', 'A']
        )


class ListItemFilterTest(BaseFilterTest):

    def get_manager(self):
        class Manager:
            ctx = unittest.mock.MagicMock()
        m = Manager()
        m.ctx.options.cache = None
        return m

    def instance(self, id_, list_):
        return {
            'id': id_,
            'list_elements': list_
        }

    def resources(self, lists):
        result = []
        for i in range(len(lists)):
            result.append(self.instance(i, lists[i]))
        return result

    def test_list_item_filter(self):
        resources = self.resources(
            [
                [{'foo': 'bar', 'bar': '0'}],
                [{'foo': 'bar', 'bar': '1'}],
                [{'foo': 'bar', 'bar': '2'}]
            ]
        )
        f = filters.factory(
            {
                'type': 'list-item',
                'key': 'list_elements',
                'attrs': [
                    {'foo': 'bar'}
                ]
            }, manager=self.get_manager()
        )
        res = f.process(resources)
        self.assertEqual(len(res), 3)

    def test_list_item_filter_match_1(self):
        resources = self.resources(
            [
                [{'foo': 'bar', 'bar': '0'}],
                [{'foo': 'bar', 'bar': '1'}],
                [{'foo': 'bar', 'bar': '2'}]
            ]
        )
        f = filters.factory(
            {
                'type': 'list-item',
                'key': 'list_elements',
                'attrs': [
                    {'foo': 'bar'},
                    {'bar': '1'}
                ]
            }, manager=self.get_manager()
        )
        res = f.process(resources)
        self.assertEqual(len(res), 1)

    def test_list_item_filter_match_bool(self):
        resources = self.resources(
            [
                [{'foo': 'bar', 'bar': '0'}],
                [{'foo': 'bar', 'bar': '1'}],
                [{'foo': 'bar', 'bar': '2'}]
            ]
        )
        f = filters.factory(
            {
                'type': 'list-item',
                'key': 'list_elements',
                'attrs': [
                    {'foo': 'bar'},
                    {'or': [
                        {'bar': '1'},
                        {'bar': '0'}
                    ]}
                ]
            }, manager=self.get_manager()
        )
        res = f.process(resources)
        self.assertEqual(len(res), 2)

    def test_list_item_filter_match_regex(self):
        resources = self.resources(
            [
                [{'foo': 'bar', 'bar': 'c7n'}],
                [{'foo': 'bar', 'bar': 'myregistry.com/c7n'}],
                [{'foo': 'bar', 'bar': 'myregistry.com/c7n'}]
            ]
        )
        f = filters.factory(
            {
                'type': 'list-item',
                'key': 'list_elements',
                'attrs': [
                    {'foo': 'bar'},
                    {
                        'not': [
                            {
                                'type': 'value',
                                'key': 'bar',
                                'value': 'myregistry.com/.*',
                                'op': 'regex'
                            }
                        ]
                    }
                ]
            }, manager=self.get_manager()
        )
        res = f.process(resources)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['list_elements'][0]['bar'], 'c7n')
        self.assertEqual(res[0]['c7n:ListItemMatches'], ['list_elements[0]'])

    def test_list_item_filter_match_empty(self):
        resources = self.resources(
            [
                [{'foo': 'bar', 'bar': 'c7n'}],
                [{'foo': 'bar', 'bar': 'myregistry.com/c7n'}],
                [{'foo': 'bar', 'bar': 'myregistry.com/c7n'}]
            ]
        )
        f = filters.factory(
            {
                'type': 'list-item',
                'key': 'baz',
                'attrs': [
                    {'foo': 'bar'},
                    {
                        'not': [
                            {
                                'type': 'value',
                                'key': 'bar',
                                'value': 'myregistry.com/.*',
                                'op': 'regex'
                            }
                        ]
                    }
                ]
            }, manager=self.get_manager()
        )
        res = f.process(resources)
        self.assertEqual(len(res), 0)

    def test_list_item_filter_match_non_list_value(self):
        resources = self.resources(
            [1, 2, 3]
        )
        f = filters.factory(
            {
                'type': 'list-item',
                'key': 'id',
                'attrs': [
                    {'foo': 'bar'},
                ]
            }, manager=self.get_manager()
        )
        with self.assertRaises(PolicyExecutionError):
            f.process(resources)

    def test_list_item_filter_match_count(self):
        resources = self.resources(
            [
                [{'foo': 'bar', 'bar': 'c7n'}, {'foo': 'bar'}, {'foo': 'bar'}, {'foo': 'bar'}],
                [{'foo': 'bar', 'bar': 'c7n'}, {'foo': 'bar'}, {'foo': 'bar'}],
                [{'foo': 'bar', 'bar': 'c7n'}, {'foo': 'bar'}],
            ]
        )
        f = filters.factory(
            {
                'type': 'list-item',
                'key': 'list_elements',
                'count': 3,
                'count_op': 'gt',
                'attrs': [
                    {'foo': 'bar'},
                ]
            }, manager=self.get_manager()
        )
        resources = f.process(resources)
        self.assertEqual(len(resources), 1)


class AnnotationSweeperTest(unittest.TestCase):
    def test_annotation_sweep_jmespath(self):
        resources = [
            {
                "metadata": {"uid": "foo"}, "c7n:annotation": "bar"
            },
            {
                "metadata": {"uid": "bar"}, "c7n:annotation": "bar"
            },
            {
                "metadata": {"uid": "baz"},
            }
        ]
        sweeper = AnnotationSweeper(
            id_key="metadata.uid", resources=resources)
        sweeper.sweep(resources=resources)
        self.assertEqual(len(resources), 3)
        for r in resources:
            self.assertTrue("c7n:annotation" not in resources)

    def test_annotation_sweep_jmespath_no_annotations(self):
        resources = [
            {
                "metadata": {"uid": "foo"},
            },
            {
                "metadata": {"uid": "bar"},
            }
        ]
        swept = copy.deepcopy(resources)
        sweeper = AnnotationSweeper(
            id_key="metadata.uid", resources=swept)
        sweeper.sweep(resources=swept)
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources, swept)


if __name__ == "__main__":
    unittest.main()
