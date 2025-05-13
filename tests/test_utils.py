# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import ipaddress
import os
import tempfile
import time
from unittest import mock

from botocore.exceptions import ClientError
from dateutil.parser import parse as parse_date

from c7n import query
from c7n import utils
from c7n.config import Config
from .common import BaseTest


class TestTesting(BaseTest):

    def test_assert_regex(self):
        self.assertRaises(
            AssertionError,
            self.assertRegex,
            "^hello", "not hello world")


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
        count = 0
        while (count < 100000):
            count += 1
            for idx, i in enumerate(utils.backoff_delays(1, 256, jitter=True)):
                maxv = 2 ** idx
                self.assertTrue(i >= maxv / 5)
                self.assertTrue(i < maxv)


class UrlConfTest(BaseTest):

    def test_parse_url(self):
        self.assertEqual(
            dict(utils.parse_url_config('aws://target?format=json&region=us-west-2')),
            dict(url='aws://target?format=json&region=us-west-2',
                 netloc='target',
                 path='',
                 scheme='aws',
                 region='us-west-2',
                 format='json'))

        self.assertEqual(
            dict(utils.parse_url_config('')),
            {
                'netloc': '',
                'path': '',
                'scheme': '',
                'url': ''
            })

        self.assertEqual(
            dict(utils.parse_url_config('aws')),
            {
                'path': '',
                'scheme': 'aws',
                'netloc': '',
                'url': 'aws://'
            })

        self.assertEqual(
            dict(utils.parse_url_config('aws://')),
            {
                'path': '',
                'scheme': 'aws',
                'netloc': '',
                'url': 'aws://'
            })

        self.assertEqual(
            dict(utils.parse_url_config('http://example.com:8080')),
            dict(url='http://example.com:8080',
                 netloc='example.com:8080',
                 path='',
                 scheme='http'))


class ProxyUrlTest(BaseTest):
    @mock.patch('c7n.utils.getproxies', return_value={})
    def test_no_proxy(self, get_proxies_mock):
        self.assertEqual(None, utils.get_proxy_url('http://web.site'))

    def test_http_proxy_with_full_url(self):
        with mock.patch.dict(os.environ,
                             {'http_proxy': 'http://mock.http.proxy.server:8000'},
                             clear=True):
            proxy_url = utils.get_proxy_url('http://web.site')
            self.assertEqual(proxy_url, 'http://mock.http.proxy.server:8000')

    def test_http_proxy_with_relative_url(self):
        with mock.patch.dict(os.environ,
                             {'http_proxy': 'http://mock.http.proxy.server:8000'},
                             clear=True):
            proxy_url = utils.get_proxy_url('/relative/url')
            self.assertEqual(proxy_url, None)

    def test_all_proxy_with_full_url(self):
        with mock.patch.dict(os.environ,
                             {'all_proxy': 'http://mock.all.proxy.server:8000'},
                             clear=True):
            proxy_url = utils.get_proxy_url('http://web.site')
            self.assertEqual(proxy_url, 'http://mock.all.proxy.server:8000')

    def test_http_proxy_with_no_proxy_without_port(self):
        with mock.patch.dict(os.environ,
                             {
                                 'http_proxy': 'http://mock.http.proxy.server:8000',
                                 'no_proxy': '127.0.0.1,web.site,google.com',
                             },
                             clear=True):
            proxy_url = utils.get_proxy_url('http://web.site')
            self.assertEqual(proxy_url, None)

    def test_http_proxy_with_no_proxy_mismatch_explicit_port(self):
        with mock.patch.dict(os.environ,
                             {
                                 'http_proxy': 'http://mock.http.proxy.server:8000',
                                 'no_proxy': '127.0.0.1,web.site:8080,google.com',
                             },
                             clear=True):
            proxy_url = utils.get_proxy_url('http://web.site')
            self.assertEqual(proxy_url, 'http://mock.http.proxy.server:8000')

    def test_http_proxy_with_no_proxy_match_explicit_port(self):
        with mock.patch.dict(os.environ,
                             {
                                 'http_proxy': 'http://mock.http.proxy.server:8000',
                                 'no_proxy': '127.0.0.1,web.site:8080,google.com',
                             },
                             clear=True):
            proxy_url = utils.get_proxy_url('http://web.site:8080')
            self.assertEqual(proxy_url, None)


class UtilTest(BaseTest):

    def test_merge_dict_list(self):

        assert utils.merge_dict_list([
            {'a': 1, 'x': 0}, {'b': 2, 'x': 0}, {'c': 3, 'x': 1}]) == {
                'a': 1, 'b': 2, 'c': 3, 'x': 1}

    def test_merge_dict(self):
        a = {'detail': {'eventName': ['CreateSubnet'],
                        'eventSource': ['ec2.amazonaws.com']},
             'detail-type': ['AWS API Call via CloudTrail']}
        b = {'detail': {'userIdentity': {
            'userName': [{'anything-but': 'deputy'}]}}}
        self.assertEqual(
            utils.merge_dict(a, b),
            {'detail-type': ['AWS API Call via CloudTrail'],
             'detail': {
                 'eventName': ['CreateSubnet'],
                 'eventSource': ['ec2.amazonaws.com'],
                 'userIdentity': {
                     'userName': [
                         {'anything-but': 'deputy'}]}}})

    def test_merge_dict_iam_condition(self):
        a = {
            "Bool": {
                "aws:SecureTransport": "true",
            },
            "StringNotLike": {
                "aws": "abc"
            },
            "StringEquals": {
                "aws:PrincipalType": "AssumedRole"
            },
            "StringLike": {
                "aws": ["def", "ghi"]
            },
            "StringNotLike": {
                "aws": "tsr"
            }
            }
        b = {
            "StringNotLike": {
                "aws": "def"
            },
            "Bool": {
                "elasticfilesystem:AccessedViaMountTarget": "true",
                "aws:SecureTransport": "false"
            },
            "StringEquals": {
                "aws:PrincipalType": [
                    "AssumedRole",
                    "User",
                    "Account"
                ]
            },
            "StringLike": {
                "aws": "abc"
            },
            "StringNotLike": {
                "aws": ["zyx", "wvu"]
            }
            }

        self.assertEqual(
            utils.merge_dict(a, b),
            {
                "Bool": {
                    "aws:SecureTransport": "true",
                    "elasticfilesystem:AccessedViaMountTarget": "true",
                },
                "StringNotLike": {
                    "aws": "abc"
                },
                "StringEquals": {
                    "aws:PrincipalType": [
                        "AssumedRole",
                        "User",
                        "Account"
                    ]
                },
                "StringLike": {
                    "aws": ["def", "ghi", "abc"]
                },
                "StringNotLike": {
                    "aws": ["tsr","zyx", "wvu"]
                }
            }
        )
    def test_merge_dict_exception(self):

        a = {
            "a": ["bcd"]
        }
        b = {
            "a": {"abc": 123}
        }
        with self.assertRaises(Exception):
            utils.merge_dict(a,b)


    def test_compare_dicts_using_sets(self):
        a = {
                "Bool": {
                    "aws:SecureTransport": "true",
                    "elasticfilesystem:AccessedViaMountTarget": "true",
                },
                "StringNotLike": {
                    "aws": "abc"
                },
                "StringEquals": {
                    "aws:PrincipalType": [
                        "AssumedRole",
                        "User",
                        "Account"
                    ]
                },
                "StringNotEquals": {
                    "aws:PrincipalType": [
                        "Anonymous",
                        "User"
                    ]
                }
            }
        b = {
            "StringNotLike": {
                "aws": ["abc"]
            },
            "Bool": {
                "elasticfilesystem:AccessedViaMountTarget": "true",
                "aws:SecureTransport": "true"
            },
            "StringEquals": {
                "aws:PrincipalType": [
                    "User",
                    "AssumedRole",
                    "Account"
                ]
            },
            "StringNotEquals": {
                "aws:PrincipalType": [
                    "Anonymous",
                    "User"
                ]
            }
            }
        self.assertTrue(utils.compare_dicts_using_sets(a, b))

    def test_format_to_set(self):
        self.assertEqual(utils.format_to_set("abcd"), {"abcd"})
        self.assertEqual(utils.format_to_set(["abc", "def"]), {"abc", "def"})
        self.assertEqual(utils.format_to_set(123), 123)
        self.assertEqual(utils.format_to_set(True), True)
        self.assertEqual(utils.format_to_set(False), False)

    def test_format_dict_with_sets(self):
        a = {
                "Bool": {
                    "aws:SecureTransport": "true",
                    "elasticfilesystem:AccessedViaMountTarget": "true",
                },
                "StringNotLike": {
                    "aws": "abc"
                },
                "StringEquals": {
                    "aws:PrincipalType": [
                        "AssumedRole",
                        "User",
                        "Account"
                    ]
                },
                "StringNotEquals": {
                    "aws:PrincipalType": [
                        "Anonymous",
                        "User"
                    ]
                }
            }
        self.assertEqual(utils.format_dict_with_sets(a),
            {
                "Bool": {
                    "aws:SecureTransport": {"true"},
                    "elasticfilesystem:AccessedViaMountTarget": {"true"},
                },
                "StringNotLike": {
                    "aws": {"abc"}
                },
                "StringEquals": {
                    "aws:PrincipalType": {
                        "AssumedRole",
                        "User",
                        "Account"
                    }
                },
                "StringNotEquals": {
                    "aws:PrincipalType": {
                        "Anonymous",
                        "User"
                    }
                }
            }
            )
        self.assertEqual(utils.format_dict_with_sets("abc"), "abc")

    def test_local_session_region(self):
        policies = [
            self.load_policy(
                {'name': 'ec2', 'resource': 'ec2'},
                config=Config.empty(region="us-east-1")),
            self.load_policy(
                {'name': 'ec2', 'resource': 'ec2'},
                config=Config.empty(region='us-west-2'))]
        previous = None
        previous_region = None
        for p in policies:
            self.assertEqual(p.options.region, p.session_factory.region)
            session = utils.local_session(p.session_factory)
            self.assertNotEqual(session.region_name, previous_region)
            self.assertNotEqual(session, previous)
            previous = session
            previous_region = p.options.region

        self.assertEqual(utils.local_session(p.session_factory), previous)

    def test_encode_bytes(self):
        self.assertEqual(
            json.loads(json.dumps(
                {"bytes": b"123"}, cls=utils.JsonEncoder)),
                {'bytes': '123'}
            )

    def test_format_date(self):
        d = parse_date("2018-02-02 12:00")
        self.assertEqual("{}".format(utils.FormatDate(d)), "2018-02-02 12:00:00")

        self.assertEqual("{:%Y-%m-%d}".format(utils.FormatDate(d)), "2018-02-02")

        self.assertEqual("{:+5h%H}".format(utils.FormatDate(d)), "17")

        self.assertEqual("{:+5d%d}".format(utils.FormatDate(d)), "07")

        self.assertEqual("{:+5M%M}".format(utils.FormatDate(d)), "05")

        self.assertEqual(json.dumps(utils.FormatDate(d),
                                    cls=utils.JsonEncoder, indent=2),
                         '"2018-02-02T12:00:00"')
        self.assertEqual(str(d), '2018-02-02 12:00:00')

    def test_group_by(self):
        items = [{}, {"Type": "a"}, {"Type": "a"}, {"Type": "b"}]
        self.assertEqual(list(utils.group_by(items, "Type").keys()), [None, "a", "b"])
        items = [
            {},
            {"Type": {"Part": "a"}},
            {"Type": {"Part": "a"}},
            {"Type": {"Part": "b"}},
        ]
        self.assertEqual(list(utils.group_by(items, "Type.Part").keys()), [None, "a", "b"])

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

    def test_ipv4_list(self):
        n1 = utils.IPv4Network(u"10.0.0.0/16")
        n2 = utils.IPv4Network(u"10.0.1.0/24")
        n3 = utils.IPv4Network(u"10.0.0.5/32")
        n4 = utils.IPv4Network(u"192.168.1.0/24")
        IPV4_list = utils.IPv4List([n1, n2])
        self.assertTrue(n3 in IPV4_list)
        self.assertFalse(n4 in IPV4_list)

        a1 = ipaddress.ip_address(u"10.0.1.16")
        self.assertTrue(a1 in IPV4_list)
        self.assertTrue(a1 in utils.IPv4List([a1, n4]))

        IPV4_list2 = utils.IPv4List([n3, n4])
        self.assertFalse(a1 in IPV4_list2)

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
            utils.generate_arn("s3", "my_bucket", region="us-gov-west-1"),
            "arn:aws-us-gov:s3:::my_bucket"
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

    def test_camel_case_implicit(self):
        d = {'ownerId': 'abc',
             'modifyDateIso': '2021-01-05T13:43:26.749906',
             'createTimeMillis': '1609854135165',
             'createTime': '1609854135'}
        r = utils.camelResource(d, implicitTitle=False, implicitDate=True)
        assert set(r) == {'ownerId', 'modifyDateIso', 'createTimeMillis', 'createTime'}
        r.pop('ownerId')
        for k in r:
            assert r[k].strftime('%Y/%m/%d') == '2021/01/05'

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
        dtdec = utils.JsonEncoder()
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

        class FakeResource:
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
        self.assertIsInstance(ret, str)

        delattr(FakeResource, "schema")
        ret = utils.reformat_schema(FakeResource)
        self.assertIsInstance(ret, str)

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

    def test_get_support_region(self):
        # AWS Partition
        mock_manager = mock.MagicMock()
        mock_manager.config.region = "us-east-1"
        res = utils.get_support_region(mock_manager)
        self.assertEqual("us-east-1", res)

        mock_manager.config.region = "us-west-2"
        res = utils.get_support_region(mock_manager)
        self.assertEqual("us-east-1", res)

        mock_manager.config.region = "eu-west-1"
        res = utils.get_support_region(mock_manager)
        self.assertEqual("us-east-1", res)

        # GovCloud Partition
        mock_manager.config.region = "us-gov-west-1"
        res = utils.get_support_region(mock_manager)
        self.assertEqual("us-gov-west-1", res)

        mock_manager.config.region = "us-gov-east-1"
        res = utils.get_support_region(mock_manager)
        self.assertEqual("us-gov-west-1", res)

        # AWS CN Partition
        mock_manager.config.region = "cn-northwest-1"
        res = utils.get_support_region(mock_manager)
        self.assertEqual("cn-north-1", res)

        mock_manager.config.region = "cn-north-1"
        res = utils.get_support_region(mock_manager)
        self.assertEqual("cn-north-1", res)

    def test_get_resource_tagging_region(self):

        resource_type = query.TypeInfo()

        # Regional endpoint checks
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'us-east-2'), 'us-east-2')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'ap-southeast-1'), 'ap-southeast-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'eu-west-1'), 'eu-west-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'us-gov-east-1'), 'us-gov-east-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'cn-north-1'), 'cn-north-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'us-iso-east-1'), 'us-iso-east-1')

        # Global resource checks
        resource_type.global_resource = True

        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'us-east-2'), 'us-east-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'us-gov-east-1'), 'us-gov-west-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'cn-north-1'), 'cn-north-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'us-iso-east-1'), 'us-iso-east-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                           'ap-southeast-1'), 'us-east-1')
        self.assertEqual(utils.get_resource_tagging_region(resource_type,
                                                              'eu-west-1'), 'us-east-1')

    def test_get_eni_resource_type(self):
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Attachment": {"InstanceId": "i-0e040de7dfabbcc8c"}, "Description": ""}),
            'ec2')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "ELB app/test-alb/3d20737b50b4b66e"}),
            'elb-app')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "ELB net/test-nlb/c973bda47de90e99"}),
            'elb-net')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "ELB gwy/test-glb/3a85ce44e6caa0af"}),
            'elb-gwy')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "ELB test-elb"}),
            'elb')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "ENI managed by APIGateway"}),
            'apigw')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "AWS CodeStar Connections"}),
            'codestar')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "DAX"}),
            'dax')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "AWS created network interface for directory"}),
            'dir')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "DMSNetworkInterface"}),
            'dms')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "arn:aws:ecs:us-west-2:123456789012:attachment/XXXX"}),
            'ecs')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "EFS mount target for fs-f9b8d350 (fsmt-b716661e)"}),
            'fsmt')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "ElastiCache test-1"}),
            'elasticache')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "AWS ElasticMapReduce"}),
            'emr')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "CloudHSM Managed Interface"}),
            'hsm')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "CloudHsm ENI"}),
            'hsmv2')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "AWS Lambda VPC ENI-test-XXX"}),
            'lambda')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "Interface for NAT Gateway nat-06f54d43caf44bf8d"}),
            'nat')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "RDSNetworkInterface"}),
            'rds')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "Network interface for DBProxy proxy-XXX-database-1"}),
            'rds')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "RedshiftNetworkInterface"}),
            'redshift')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "Network Interface for Transit Gateway Attachment tgw-attach-XXX"}),
            'tgw')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": "VPC Endpoint Interface vpce-0472c5d3fc4ce1de4"}),
            'vpce')
        self.assertEqual(
            utils.get_eni_resource_type(
                {"Description": ""}),
            'unknown')


def test_parse_date_floor():
    # bulk of parse date tests are actually in test_filters
    assert utils.parse_date(30) is None
    assert utils.parse_date(1) is None
    assert utils.parse_date('3000') is None
    assert utils.parse_date('30') is None


def test_output_path_join():
    assert utils.join_output_path(
        's3://cross-region-c7n/iam-check?region=us-east-2',
        'Samuel',
        'us-east-1'
    ) == 's3://cross-region-c7n/iam-check/Samuel/us-east-1?region=us-east-2'

    output_dir = 's3://cross-region-c7n/iam-checks/{account}/{now:%Y-%m}/{uuid}'
    assert utils.join_output_path(output_dir, 'Samuel', 'us-east-1') == output_dir

    output_dir = './local-dir'
    assert utils.join_output_path(output_dir, 'Samuel', 'us-east-1') == (
        f"./local-dir{os.sep}Samuel{os.sep}us-east-1")


def test_jmespath_parse_split():
    result = utils.jmespath_search(
        'foo.bar | split(`.`, @)',
        {'foo': {'bar': 'abc.xyz'}}
    )
    assert result == ['abc', 'xyz']

    compiled = utils.jmespath_compile(
        'foo.bar | split(`.`, @)',
    )
    assert isinstance(compiled, utils.ParsedResultWithOptions)
    result = compiled.search(
        {'foo': {'bar': 'abc.xyz'}}
    )
    assert result == ['abc', 'xyz']


def test_jmespath_parse_to_json():
    result = utils.jmespath_search(
        'from_json(foo).bar',
        {'foo': '{"bar": "abc.xyz"}'}
    )
    assert result == 'abc.xyz'

    # bad json comes in = return null
    result = utils.jmespath_search(
        'from_json(foo).bar',
        {'foo': '{"]}'}
    )
    assert result is None
