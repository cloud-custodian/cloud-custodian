# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import csv
import json
import pickle
import os
import tempfile
import vcr
from urllib.request import urlopen

from .common import BaseTest, ACCOUNT_ID, Bag
from .test_s3 import destroyBucket

from c7n.cache import SqlKvCache
from c7n.config import Config
from c7n.resolver import ValuesFrom, URIResolver

from pytest_terraform import terraform


class FakeCache:

    def __init__(self):
        self.state = {}
        self.gets = 0
        self.saves = 0

    def get(self, key):
        self.gets += 1
        return self.state.get(pickle.dumps(key))

    def save(self, key, data):
        self.saves += 1
        self.state[pickle.dumps(key)] = data

    def load(self):
        return True

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kw):
        return


class FakeResolver:

    def __init__(self, contents):
        if isinstance(contents, bytes):
            contents = contents.decode("utf8")
        self.contents = contents

    def resolve(self, uri, headers):
        return self.contents


@terraform('dynamodb_resolver')
def test_dynamodb_resolver(test, dynamodb_resolver):
    factory = test.replay_flight_data("test_dynamodb_resolver")
    manager = Bag(session_factory=factory, _cache=None,
                  config=Bag(account_id="123", region="us-east-1"))
    resolver = ValuesFrom({
        "url": "dynamodb",
        "query": f'select app_name from "{dynamodb_resolver["aws_dynamodb_table.apps.name"]}"',
    }, manager)

    values = resolver.get_values()
    assert values == ["cicd", "app1"]


@terraform('dynamodb_resolver_multi')
def test_dynamodb_resolver_multi(test, dynamodb_resolver_multi):
    factory = test.replay_flight_data("test_dynamodb_resolver_multi")
    manager = Bag(session_factory=factory, _cache=None,
                  config=Bag(account_id="123", region="us-east-1"))
    resolver = ValuesFrom({
        "url": "dynamodb",
        "query": (
            f'select app_name, env from "{dynamodb_resolver_multi["aws_dynamodb_table.apps.name"]}"'
        ),
        "expr": "[].env"
    }, manager)

    values = resolver.get_values()
    assert set(values) == {"shared", "prod"}


def test_dynamodb_resolver_complex_records():
    """Test DynamoDB resolver with complex records requiring resource value processing.

    This test specifically ensures coverage for line 165 in resolver.py that calls
    _get_resource_values when record_singleton is False or there is an expr.
    """
    from unittest.mock import patch, MagicMock

    # Create a mock manager
    manager = Bag(
        session_factory=lambda: None,
        _cache=None,
        config=Bag(account_id="123", region="us-east-1")
    )

    # Create a ValuesFrom object with complex records (not singleton)
    # and an expression to process them
    resolver = ValuesFrom({
        "url": "dynamodb",
        "query": 'select id, name, status from "test_table"',
        "expr": "[?status=='active'].id"
    }, manager)

    # Create mock data that will ensure record_singleton is False
    # and that _get_resource_values is called
    mock_items = [
        {"id": {"S": "id1"}, "name": {"S": "name1"}, "status": {"S": "active"}},
        {"id": {"S": "id2"}, "name": {"S": "name2"}, "status": {"S": "inactive"}},
        {"id": {"S": "id3"}, "name": {"S": "name3"}, "status": {"S": "active"}}
    ]

    # Create a mock paginator response
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Items": mock_items}]

    # Create a mock client that returns our mock paginator
    mock_client = MagicMock()
    mock_client.meta.service_model.operation_model.return_value = MagicMock()

    # Create a mock Paginator constructor
    mock_paginator_cls = MagicMock(return_value=mock_paginator)

    # Create a dummy deserializer that converts DynamoDB format to Python objects
    class MockDeserializer:
        def deserialize(self, value):
            # Simple deserializer that extracts value from DynamoDB format
            return next(iter(value.values()))

    # Patch the necessary functions
    with patch('c7n.resolver.local_session', return_value=mock_client), \
         patch('botocore.paginate.Paginator', mock_paginator_cls), \
         patch('boto3.dynamodb.types.TypeDeserializer', return_value=MockDeserializer()):

        # Add a spy on _get_resource_values to verify it gets called
        original_get_resource_values = resolver._get_resource_values
        called = [False]

        def spy_get_resource_values(data):
            called[0] = True
            return original_get_resource_values(data)

        resolver._get_resource_values = spy_get_resource_values

        # Call get_values which should trigger our mocked path
        _ = resolver.get_values()

        # Verify _get_resource_values was called (line 165 coverage)
        assert called[0], "Line 165 (_get_resource_values call) was not executed"

        # Reset the method
        resolver._get_resource_values = original_get_resource_values


class ResolverTest(BaseTest):

    def test_resolve_s3(self):
        session_factory = self.replay_flight_data("test_s3_resolver")
        session = session_factory()
        client = session.client("s3")
        resource = session.resource("s3")

        bname = "custodian-byebye"
        client.create_bucket(Bucket=bname)
        self.addCleanup(destroyBucket, client, bname)

        key = resource.Object(bname, "resource.json")
        content = json.dumps({"moose": {"soup": "duck"}})
        key.put(
            Body=content, ContentLength=len(content), ContentType="application/json"
        )

        cache = FakeCache()
        resolver = URIResolver(session_factory, cache)
        uri = "s3://%s/resource.json?RequestPayer=requestor" % bname
        data = resolver.resolve(uri, {})
        self.assertEqual(content, data)
        self.assertEqual(list(cache.state.keys()), [pickle.dumps(("uri-resolver", uri))])

    def test_handle_content_encoding(self):
        session_factory = self.replay_flight_data("test_s3_resolver")
        cache = FakeCache()
        resolver = URIResolver(session_factory, cache)
        uri = "http://httpbin.org/gzip"
        with vcr.use_cassette('tests/data/vcr_cassettes/test_resolver.yaml'):
            response = urlopen(uri)
            content = resolver.handle_response_encoding(response)
            data = json.loads(content)
            self.assertEqual(data['gzipped'], True)
            self.assertEqual(response.headers['Content-Encoding'], 'gzip')

    def test_resolve_file(self):
        content = json.dumps({"universe": {"galaxy": {"system": "sun"}}})
        cache = FakeCache()
        resolver = URIResolver(None, cache)
        with tempfile.NamedTemporaryFile(mode="w+", dir=os.getcwd(), delete=False) as fh:
            self.addCleanup(os.unlink, fh.name)
            fh.write(content)
            fh.flush()
            self.assertEqual(resolver.resolve("file:%s" % fh.name, {'auth': 'token'}), content)


def test_value_from_sqlkv(tmp_path):

    kv = SqlKvCache(Bag(cache=tmp_path / "cache.db", cache_period=60))
    config = Config.empty(account_id=ACCOUNT_ID)
    mgr = Bag({"session_factory": None, "_cache": kv, "config": config})
    values = ValuesFrom(
        {"url": "moon", "expr": "[].bean", "format": "json"}, mgr)
    values.resolver = FakeResolver(json.dumps([{"bean": "magic"}]))
    assert values.get_values() == {"magic"}
    assert values.get_values() == {"magic"}


class UrlValueTest(BaseTest):

    def setUp(self):
        self.old_dir = os.getcwd()
        os.chdir(tempfile.gettempdir())

    def tearDown(self):
        os.chdir(self.old_dir)

    def get_values_from(self, data, content, cache=None):
        config = Config.empty(account_id=ACCOUNT_ID)
        mgr = Bag({"session_factory": None, "_cache": cache, "config": config})
        values = ValuesFrom(data, mgr)
        values.resolver = FakeResolver(content)
        return values

    def test_none_json_expr(self):
        values = self.get_values_from(
            {"url": "moon", "expr": "mars", "format": "json"},
            json.dumps([{"bean": "magic"}]),
        )
        self.assertEqual(values.get_values(), None)

    def test_empty_json_expr(self):
        values = self.get_values_from(
            {"url": "moon", "expr": "[].mars", "format": "json"},
            json.dumps([{"bean": "magic"}]),
        )
        self.assertEqual(values.get_values(), set())

    def test_json_expr(self):
        values = self.get_values_from(
            {"url": "moon", "expr": "[].bean", "format": "json"},
            json.dumps([{"bean": "magic"}]),
        )
        self.assertEqual(values.get_values(), {"magic"})

    def test_invalid_format(self):
        values = self.get_values_from({"url": "mars"}, "")
        self.assertRaises(ValueError, values.get_values)

    def test_txt(self):
        with open("resolver_test.txt", "w") as out:
            for i in ["a", "b", "c", "d"]:
                out.write("%s\n" % i)
        with open("resolver_test.txt", "rb") as out:
            values = self.get_values_from({"url": "letters.txt"}, out.read())
        os.remove("resolver_test.txt")
        self.assertEqual(values.get_values(), {"a", "b", "c", "d"})

    def test_csv_expr(self):
        with open("test_expr.csv", "w") as out:
            writer = csv.writer(out)
            writer.writerows([range(5) for r in range(5)])
        with open("test_expr.csv", "rb") as out:
            values = self.get_values_from(
                {"url": "sun.csv", "expr": "[*][2]"}, out.read()
            )
        os.remove("test_expr.csv")
        self.assertEqual(values.get_values(), {"2"})

    def test_csv_none_expr(self):
        with open("test_expr.csv", "w") as out:
            writer = csv.writer(out)
            writer.writerows([range(5) for r in range(5)])
        with open("test_expr.csv", "rb") as out:
            values = self.get_values_from(
                {"url": "sun.csv", "expr": "DNE"}, out.read()
            )
        os.remove("test_expr.csv")
        self.assertEqual(values.get_values(), None)

    def test_csv_expr_using_dict(self):
        with open("test_dict.csv", "w") as out:
            writer = csv.writer(out)
            writer.writerow(["aa", "bb", "cc", "dd", "ee"])  # header row
            writer.writerows([range(5) for r in range(5)])
        with open("test_dict.csv", "rb") as out:
            values = self.get_values_from(
                {"url": "sun.csv", "expr": "bb[1]", "format": "csv2dict"}, out.read()
            )
        os.remove("test_dict.csv")
        self.assertEqual(values.get_values(), "1")

    def test_csv_none_expr_using_dict(self):
        with open("test_dict.csv", "w") as out:
            writer = csv.writer(out)
            writer.writerow(["aa", "bb", "cc", "dd", "ee"])  # header row
            writer.writerows([range(5) for r in range(5)])
        with open("test_dict.csv", "rb") as out:
            values = self.get_values_from(
                {"url": "sun.csv", "expr": "ff", "format": "csv2dict"}, out.read()
            )
        os.remove("test_dict.csv")
        self.assertEqual(values.get_values(), None)

    def test_csv_no_expr_using_dict(self):
        with open("test_dict.csv", "w") as out:
            writer = csv.writer(out)
            writer.writerow(["aa", "bb", "cc", "dd", "ee"])  # header row
            writer.writerows([range(5) for r in range(5)])
        with open("test_dict.csv", "rb") as out:
            values = self.get_values_from(
                {"url": "sun.csv", "format": "csv2dict"}, out.read()
            )
        os.remove("test_dict.csv")
        self.assertEqual(values.get_values(), {"0", "1", "2", "3", "4"})

    def test_csv_column(self):
        with open("test_column.csv", "w") as out:
            writer = csv.writer(out)
            writer.writerows([range(5) for r in range(5)])
        with open("test_column.csv", "rb") as out:
            values = self.get_values_from({"url": "sun.csv", "expr": 1}, out.read())
        os.remove("test_column.csv")
        self.assertEqual(values.get_values(), {"1"})

    def test_csv_raw(self):
        with open("test_raw.csv", "w") as out:
            writer = csv.writer(out)
            writer.writerows([range(3, 4) for r in range(5)])
        with open("test_raw.csv", "rb") as out:
            values = self.get_values_from({"url": "sun.csv"}, out.read())
        os.remove("test_raw.csv")
        self.assertEqual(values.get_values(), {"3"})

    def test_value_from_vars(self):
        values = self.get_values_from(
            {"url": "{account_id}", "expr": '["{region}"][]', "format": "json"},
            json.dumps({"us-east-1": "east-resource"}),
        )
        self.assertEqual(values.get_values(), {"east-resource"})
        self.assertEqual(values.data.get("url", ""), ACCOUNT_ID)

    def test_value_from_caching(self):
        cache = FakeCache()
        values = self.get_values_from(
            {"url": "", "expr": '["{region}"][]', "format": "json"},
            json.dumps({"us-east-1": "east-resource"}),
            cache=cache,
        )
        self.assertEqual(values.get_values(), {"east-resource"})
        self.assertEqual(values.get_values(), {"east-resource"})
        self.assertEqual(values.get_values(), {"east-resource"})
        self.assertEqual(cache.saves, 1)
        self.assertEqual(cache.gets, 3)


def test_dynamodb_url_type():
    """Test that the dynamodb URL type is properly handled.

    This test verifies that using 'url: dynamodb' in a value_from filter
    doesn't cause an error about unknown URL type.
    """
    config = Config.empty(account_id=ACCOUNT_ID)
    mgr = Bag({"session_factory": None, "_cache": None, "config": config})

    # Verify that creating a ValuesFrom with 'url: dynamodb' doesn't raise an error
    values = ValuesFrom({
        "url": "dynamodb",
        "query": "select id from mytable",
        "format": "json",
        "expr": "[*].id"
    }, mgr)

    # Mock the _get_ddb_values method to avoid actually calling DynamoDB
    values._get_ddb_values = lambda: ["id1", "id2"]

    # Verify that get_values() doesn't raise an error
    result = values.get_values()
    assert result == ["id1", "id2"]


def test_uri_resolver_dynamodb():
    """Test that the URIResolver can handle 'dynamodb' URLs.

    This test verifies that URIResolver.resolve doesn't raise an error
    when given a 'dynamodb' URL.
    """
    resolver = URIResolver(None, FakeCache())

    # Verify that resolve() doesn't raise an error for 'dynamodb' URL
    result = resolver.resolve("dynamodb", {})

    # The result should be an empty string since the actual handling
    # is done in ValuesFrom._get_ddb_values
    assert result == ""
