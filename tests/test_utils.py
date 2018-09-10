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

import json
import os
import unittest
import sys
import tempfile
import time

from botocore.exceptions import ClientError
from dateutil.parser import parse as parse_date
import six

from c7n import ipaddress, utils

from .common import BaseTest


class Backoff(BaseTest):

    def test_retry_passthrough(self):

        def func():
            return 42

        retry = utils.get_retry((), 5)
        self.assertEqual(retry(func), 42)

    def test_retry_errors(self):
        self.patch(time, "sleep", lambda x: x)
        self.count = 0

        def func():
            self.count += 1
            raise ClientError({"Error": {"Code": 42}}, "something")

        retry = utils.get_retry((42,), 5)

        try:
            retry(func)
        except ClientError:
            self.assertEqual(self.count, 5)
        else:
            self.fail("should have raised")

    def test_delays(self):
        self.assertEqual(
            list(utils.backoff_delays(1, 256)),
            [1, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0],
        )

    def test_delays_jitter(self):
        for idx, i in enumerate(utils.backoff_delays(1, 256, jitter=True)):
            maxv = 2 ** idx
            self.assertTrue(i > 0)
            self.assertTrue(i < maxv)


class WorkerDecorator(BaseTest):

    def test_method_worker(self):

        class foo(object):

            @utils.worker
            def bar(self, err=False):
                """abc"""
                if err:
                    raise ValueError("foo")
                return 42

        i = foo()
        log_output = self.capture_logging("c7n.worker")
        self.assertEqual(i.bar(), 42)
        self.assertRaises(ValueError, i.bar, True)
        self.assertTrue(
            log_output.getvalue().startswith(
                "Error invoking tests.test_utils.bar\nTraceback"
            )
        )

    def test_function_worker(self):

        @utils.worker
        def rabbit(err=False):
            """what's up doc"""
            if err:
                raise ValueError("more carrots")
            return 42

        self.assertEqual(rabbit.__doc__, "what's up doc")
        log_output = self.capture_logging("c7n.worker")
        self.assertEqual(rabbit(), 42)
        self.assertEqual(log_output.getvalue(), "")
        self.assertRaises(ValueError, rabbit, True)
        self.assertTrue(
            log_output.getvalue().startswith(
                "Error invoking tests.test_utils.rabbit\nTraceback"
            )
        )
        self.assertTrue("more carrots" in log_output.getvalue())


class UtilTest(unittest.TestCase):

    def test_format_date(self):
        d = parse_date("2018-02-02 12:00")
        self.assertEqual("{}".format(utils.FormatDate(d)), "2018-02-02 12:00:00")

        self.assertEqual("{:%Y-%m-%d}".format(utils.FormatDate(d)), "2018-02-02")

        self.assertEqual("{:+5h%H}".format(utils.FormatDate(d)), "17")

        self.assertEqual("{:+5d%d}".format(utils.FormatDate(d)), "07")

        self.assertEqual("{:+5M%M}".format(utils.FormatDate(d)), "05")

    def test_group_by(self):
        sorter = lambda x: x  # NOQA E731
        sorter = sys.version_info.major is 2 and sorted or sorter
        items = [{}, {"Type": "a"}, {"Type": "a"}, {"Type": "b"}]
        self.assertEqual(
            sorter(list(utils.group_by(items, "Type").keys())), [None, "a", "b"]
        )
        items = [
            {},
            {"Type": {"Part": "a"}},
            {"Type": {"Part": "a"}},
            {"Type": {"Part": "b"}},
        ]
        self.assertEqual(
            sorter(list(utils.group_by(items, "Type.Part").keys())), [None, "a", "b"]
        )

    def write_temp_file(self, contents, suffix=".tmp"):
        """ Write a temporary file and return the filename.

        The file will be cleaned up after the test.
        """
        file = tempfile.NamedTemporaryFile(suffix=suffix)
        file.write(contents)
        file.flush()
        self.addCleanup(file.close)
        return file.name

    def test_ipv4_network(self):
        n1 = utils.IPv4Network(u"10.0.0.0/16")
        n2 = utils.IPv4Network(u"10.0.1.0/24")
        self.assertTrue(n2 in n1)
        self.assertFalse(n1 in n2)

        n3 = utils.IPv4Network(u"10.0.0.0/8")
        self.assertTrue(n2 in n3)
        self.assertTrue(n1 in n3)

        n4 = utils.IPv4Network(u"192.168.1.0/24")
        self.assertFalse(n4 in n3)

        a1 = ipaddress.ip_address(u"10.0.1.16")
        self.assertTrue(a1 in n1)
        self.assertTrue(a1 in n3)
        self.assertFalse(a1 in n4)

    def test_chunks(self):
        self.assertEqual(
            list(utils.chunks(range(100), size=50)),
            [list(range(50)), list(range(50, 100, 1))],
        )
        self.assertEqual(list(utils.chunks(range(1), size=50)), [[0]])
        self.assertEqual(
            list(utils.chunks(range(60), size=50)),
            [list(range(50)), list(range(50, 60, 1))],
        )

    def test_type_schema(self):
        self.assertEqual(
            utils.type_schema("tester"),
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["type"],
                "properties": {"type": {"enum": ["tester"]}},
            },
        )
        res = utils.type_schema("tester", inherits=["tested"])
        self.assertIn({"$ref": "tested"}, res["allOf"])

    def test_generate_arn(self):
        self.assertEqual(
            utils.generate_arn("s3", "my_bucket"), "arn:aws:s3:::my_bucket"
        )
        self.assertEqual(
            utils.generate_arn(
                "cloudformation",
                "MyProductionStack/abc9dbf0-43c2-11e3-a6e8-50fa526be49c",
                region="us-east-1",
                account_id="123456789012",
                resource_type="stack",
            ),
            "arn:aws:cloudformation:us-east-1:123456789012:"
            "stack/MyProductionStack/abc9dbf0-43c2-11e3-a6e8-50fa526be49c",
        )
        self.assertEqual(
            utils.generate_arn(
                "rds",
                "mysql-option-group1",
                region="us-east-1",
                account_id="123456789012",
                resource_type="og",
                separator=":",
            ),
            "arn:aws:rds:us-east-1:123456789012:og:mysql-option-group1",
        )

    def test_camel_nested(self):
        nest = {
            "description": "default VPC security group",
            "groupId": "sg-6c7fa917",
            "groupName": "default",
            "ipPermissions": [
                {
                    "ipProtocol": "-1",
                    "ipRanges": ["108.56.181.242/32"],
                    "ipv4Ranges": [{"cidrIp": "108.56.181.242/32"}],
                    "ipv6Ranges": [],
                    "prefixListIds": [],
                    "userIdGroupPairs": [
                        {"groupId": "sg-6c7fa917", "userId": "644160558196"}
                    ],
                }
            ],
            "ipPermissionsEgress": [
                {
                    "ipProtocol": "-1",
                    "ipRanges": ["0.0.0.0/0"],
                    "ipv4Ranges": [{"cidrIp": "0.0.0.0/0"}],
                    "ipv6Ranges": [],
                    "prefixListIds": [],
                    "userIdGroupPairs": [],
                }
            ],
            "ownerId": "644160558196",
            "tags": [
                {"key": "Name", "value": ""},
                {"key": "c7n-test-tag", "value": "c7n-test-val"},
            ],
            "vpcId": "vpc-d2d616b5",
        }
        self.assertEqual(
            utils.camelResource(nest)["IpPermissions"],
            [
                {
                    u"IpProtocol": u"-1",
                    u"IpRanges": [u"108.56.181.242/32"],
                    u"Ipv4Ranges": [{u"CidrIp": u"108.56.181.242/32"}],
                    u"Ipv6Ranges": [],
                    u"PrefixListIds": [],
                    u"UserIdGroupPairs": [
                        {u"GroupId": u"sg-6c7fa917", u"UserId": u"644160558196"}
                    ],
                }
            ],
        )

    def test_camel_case(self):
        d = {
            "zebraMoon": [{"instanceId": 123}, "moon"],
            "color": {"yellow": 1, "green": 2},
        }
        self.assertEqual(
            utils.camelResource(d),
            {
                "ZebraMoon": [{"InstanceId": 123}, "moon"],
                "Color": {"Yellow": 1, "Green": 2},
            },
        )

    def test_snapshot_identifier(self):
        identifier = utils.snapshot_identifier("bkup", "abcdef")
        # e.g. bkup-2016-07-27-abcdef
        self.assertEqual(len(identifier), 28)

    def test_load_error(self):
        original_yaml = utils.yaml
        utils.yaml = None
        self.assertRaises(RuntimeError, utils.yaml_load, "testing")
        utils.yaml = original_yaml

    def test_format_event(self):
        event = {"message": "This is a test", "timestamp": 1234567891011}
        event_json = (
            '{\n  "timestamp": 1234567891011, \n' '  "message": "This is a test"\n}'
        )
        self.assertEqual(json.loads(utils.format_event(event)), json.loads(event_json))

    def test_date_time_decoder(self):
        dtdec = utils.DateTimeEncoder()
        self.assertRaises(TypeError, dtdec.default, "test")

    def test_set_annotation(self):
        self.assertRaises(
            ValueError, utils.set_annotation, "not a dictionary", "key", "value"
        )

    def test_parse_s3(self):
        self.assertRaises(ValueError, utils.parse_s3, "bogus")
        self.assertEqual(utils.parse_s3("s3://things"), ("s3://things", "things", ""))

    def test_reformat_schema(self):
        # Not a real schema, just doing a smoke test of the function
        # properties = 'target'

        class FakeResource(object):
            schema = {
                "additionalProperties": False,
                "properties": {
                    "type": "foo",
                    "default": {"type": "object"},
                    "key": {"type": "string"},
                    "op": {"enum": ["regex", "ni", "gt", "not-in"]},
                    "value": {
                        "oneOf": [
                            {"type": "array"},
                            {"type": "string"},
                            {"type": "boolean"},
                            {"type": "number"},
                        ]
                    },
                },
                "required": ["key"],
            }

        ret = utils.reformat_schema(FakeResource)
        self.assertIsInstance(ret, dict)

        # Test error conditions
        # Instead of testing for specific keywords, just make sure that strings
        # are returned instead of a dictionary.
        FakeResource.schema = {}
        ret = utils.reformat_schema(FakeResource)
        self.assertIsInstance(ret, six.text_type)

        delattr(FakeResource, "schema")
        ret = utils.reformat_schema(FakeResource)
        self.assertIsInstance(ret, six.text_type)

    def test_load_file(self):
        # Basic load
        yml_file = os.path.join(os.path.dirname(__file__), "data", "vars-test.yml")
        data = utils.load_file(yml_file)
        self.assertTrue(len(data["policies"]) == 1)

        # Load with vars
        resource = "ec2"
        data = utils.load_file(yml_file, vars={"resource": resource})
        self.assertTrue(data["policies"][0]["resource"] == resource)

        # Fail to substitute
        self.assertRaises(
            utils.VarsSubstitutionError, utils.load_file, yml_file, vars={"foo": "bar"}
        )

        # JSON load
        json_file = os.path.join(os.path.dirname(__file__), "data", "ec2-instance.json")
        data = utils.load_file(json_file)
        self.assertTrue(data["InstanceId"] == "i-1aebf7c0")

    def test_format_string_values(self):
        obj = {
            "Key1": "Value1",
            "Key2": 42,
            "Key3": "{xx}",
            u"Key4": [True, {u"K": u"{yy}"}, "{xx}"],
        }
        fmt = utils.format_string_values(obj, **{"xx": "aa", "yy": "bb"})

        self.assertEqual(fmt["Key3"], "aa")
        self.assertEqual(fmt["Key4"][2], "aa")
        self.assertEqual(fmt["Key4"][1]["K"], "bb")

        self.assertEqual(
            utils.format_string_values(
                {'k': '{1}'}),
            {'k': '{1}'})

        self.assertEqual(
            utils.format_string_values(
                {'k': '{limit}',
                 'b': '{account_id}'}, account_id=21),
            {'k': '{limit}',
             'b': '21'})
