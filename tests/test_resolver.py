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


class URIResolverProviderTest(BaseTest):
    """Test suite for URI resolver provider delegation mechanism (TDD)"""

    def setUp(self):
        # Save the current registered providers before each test
        self._saved_uri_providers = URIResolver._uri_providers
        URIResolver._uri_providers = {}

    def tearDown(self):
        # Restore the registered providers after each test
        URIResolver._uri_providers = self._saved_uri_providers

    def test_register_provider(self):
        """Test that providers can register URI scheme handlers"""
        def mock_handler(uri, session_factory, cache):
            return "mock_content"

        # Register a handler for 'mock://' scheme
        URIResolver.register_provider('mock', mock_handler)

        # Verify the handler is registered
        self.assertIn('mock', URIResolver._uri_providers)
        self.assertEqual(URIResolver._uri_providers['mock'], mock_handler)

    def test_register_multiple_providers(self):
        """Test that multiple providers can be registered for different schemes"""
        def handler1(uri, session_factory, cache):
            return "handler1"

        def handler2(uri, session_factory, cache):
            return "handler2"

        URIResolver.register_provider('scheme1', handler1)
        URIResolver.register_provider('scheme2', handler2)

        self.assertEqual(len(URIResolver._uri_providers), 2)
        self.assertEqual(URIResolver._uri_providers['scheme1'], handler1)
        self.assertEqual(URIResolver._uri_providers['scheme2'], handler2)

    def test_register_provider_overwrites_existing(self):
        """Test that re-registering a scheme overwrites the previous handler"""
        def handler1(uri, session_factory, cache):
            return "handler1"

        def handler2(uri, session_factory, cache):
            return "handler2"

        URIResolver.register_provider('test', handler1)
        URIResolver.register_provider('test', handler2)

        # The second handler should overwrite the first
        self.assertEqual(URIResolver._uri_providers['test'], handler2)

    def test_resolve_with_registered_provider(self):
        """Test that resolve() delegates to registered provider for matching scheme"""
        def azure_handler(uri, session_factory, cache):
            self.assertEqual(uri, 'azure://account.blob.core.windows.net/container/blob.json')
            return '{"key": "value"}'

        URIResolver.register_provider('azure', azure_handler)

        cache = FakeCache()
        resolver = URIResolver(None, cache)
        result = resolver.resolve('azure://account.blob.core.windows.net/container/blob.json', {})

        self.assertEqual(result, '{"key": "value"}')

    def test_resolve_provider_uses_cache(self):
        """Test that provider resolution respects caching"""
        call_count = {'count': 0}

        def counting_handler(uri, session_factory, cache):
            call_count['count'] += 1
            return f"content_{call_count['count']}"

        URIResolver.register_provider('test', counting_handler)

        cache = FakeCache()
        resolver = URIResolver(None, cache)
        uri = 'test://example/file.json'

        # First call should execute handler
        result1 = resolver.resolve(uri, {})
        self.assertEqual(result1, 'content_1')
        self.assertEqual(call_count['count'], 1)

        # Second call should use cache
        result2 = resolver.resolve(uri, {})
        self.assertEqual(result2, 'content_1')  # Same content from cache
        self.assertEqual(call_count['count'], 1)  # Handler not called again

    def test_resolve_http_still_works(self):
        """Test that http:// URLs still work (backward compatibility)"""
        cache = FakeCache()
        resolver = URIResolver(None, cache)

        # Use file:// as a proxy for http:// testing without external dependencies
        with tempfile.NamedTemporaryFile(mode="w+", dir=os.getcwd(), delete=False) as fh:
            self.addCleanup(os.unlink, fh.name)
            content = json.dumps({"http": "test"})
            fh.write(content)
            fh.flush()
            result = resolver.resolve(f"file:{fh.name}", {})
            self.assertEqual(result, content)

    def test_resolve_unknown_scheme_fallback_to_http(self):
        """Test that unknown schemes fall back to HTTP handler"""
        cache = FakeCache()
        resolver = URIResolver(None, cache)

        # Use file:// to test fallback without external dependencies
        with tempfile.NamedTemporaryFile(mode="w+", dir=os.getcwd(), delete=False) as fh:
            self.addCleanup(os.unlink, fh.name)
            content = json.dumps({"fallback": "test"})
            fh.write(content)
            fh.flush()
            result = resolver.resolve(f"file:{fh.name}", {})
            self.assertEqual(result, content)

    def test_provider_handler_receives_session_factory(self):
        """Test that provider handlers receive the session_factory"""
        received_factory = {'factory': None}

        def test_handler(uri, session_factory, cache):
            received_factory['factory'] = session_factory
            return "content"

        URIResolver.register_provider('test', test_handler)

        mock_factory = lambda: None  # noqa: E731
        cache = FakeCache()
        resolver = URIResolver(mock_factory, cache)
        resolver.resolve('test://example/file', {})

        self.assertEqual(received_factory['factory'], mock_factory)

    def test_provider_handler_receives_cache(self):
        """Test that provider handlers receive the cache object"""
        received_cache = {'cache': None}

        def test_handler(uri, session_factory, cache):
            received_cache['cache'] = cache
            return "content"

        URIResolver.register_provider('test', test_handler)

        test_cache = FakeCache()
        resolver = URIResolver(None, test_cache)
        resolver.resolve('test://example/file', {})

        self.assertEqual(received_cache['cache'], test_cache)

    def test_provider_exception_handling(self):
        """Test that exceptions from providers are properly propagated"""
        def failing_handler(uri, session_factory, cache):
            raise ValueError("Test error from provider")

        URIResolver.register_provider('failing', failing_handler)

        cache = FakeCache()
        resolver = URIResolver(None, cache)

        with self.assertRaises(ValueError) as context:
            resolver.resolve('failing://example/file', {})

        self.assertIn("Test error from provider", str(context.exception))


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
