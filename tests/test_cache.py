# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from argparse import Namespace
from datetime import datetime, timedelta
import os
import pickle
import sqlite3
import sys
from unittest import TestCase

import pytest

from c7n import cache, config


class TestCache(TestCase):

    def test_factory(self):
        self.assertIsInstance(cache.factory(None), cache.NullCache)
        test_config = Namespace(cache_period=60, cache="test-cloud-custodian.cache")
        self.assertIsInstance(cache.factory(test_config), cache.SqlKvCache)
        test_config.cache = None
        self.assertIsInstance(cache.factory(test_config), cache.NullCache)


class MemCacheTest(TestCase):

    def test_mem_factory(self):
        self.assertEqual(
            cache.factory(config.Bag(cache='memory', cache_period=5)).__class__,
            cache.InMemoryCache)

    def test_get_set(self):
        mem_cache = cache.InMemoryCache({})
        mem_cache.save({'region': 'us-east-1'}, {'hello': 'world'})
        self.assertEqual(mem_cache.size(), 1)
        self.assertEqual(mem_cache.load(), True)

        mem_cache = cache.InMemoryCache({})
        self.assertEqual(
            mem_cache.get({'region': 'us-east-1'}),
            {'hello': 'world'})
        mem_cache.close()


def test_sqlkv(tmp_path):
    kv = cache.SqlKvCache(config.Bag(cache=tmp_path / "cache.db", cache_period=60))
    kv.load()
    k1 = {"account": "12345678901234", "region": "us-west-2", "resource": "ec2"}
    v1 = [{'id': 'a'}, {'id': 'b'}]

    assert kv.get(k1) is None
    kv.save(k1, v1)
    assert kv.get(k1) == v1
    kv.close()


def test_sqlkv_get_expired(tmp_path):
    kv = cache.SqlKvCache(config.Bag(cache=tmp_path / "cache.db", cache_period=60))
    kv.load()
    kv1 = {'a': 'b', 'c': 'd'}
    kv.save(kv1, kv1, datetime.utcnow() - timedelta(days=10))
    assert kv.get(kv1) is None


def test_sqlkv_load_gc(tmp_path):
    kv = cache.SqlKvCache(config.Bag(cache=tmp_path / "cache.db", cache_period=60))

    # seed old values with manual connection
    kv.conn = sqlite3.connect(kv.cache_path)
    kv.conn.execute(kv.create_table)
    kv1 = {'a': 'b', 'c': 'd'}
    kv2 = {'b': 'a', 'd': 'c'}
    kv.save(kv1, kv1, datetime.utcnow() - timedelta(days=10))
    kv.save(kv2, kv2, datetime.utcnow() - timedelta(minutes=5))

    kv.load()
    assert kv.get(kv1) is None
    assert kv.get(kv2) == kv2


def test_sqlkv_parent_dir_create(tmp_path):
    cache_path = tmp_path / ".cache" / "cache.db"
    kv = cache.SqlKvCache(config.Bag(cache=cache_path, cache_period=60))
    kv.load()
    assert os.path.exists(os.path.dirname(cache_path))


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason="windows can't remove a recently created but closed file")
def test_sqlkv_convert(tmp_path):
    cache_path = tmp_path / "cache2.db"
    with open(cache_path, 'wb') as fh:
        pickle.dump({'kv': 'abc'}, fh)
        fh.close()
    kv = cache.SqlKvCache(config.Bag(cache=cache_path, cache_period=60))
    kv.load()
    kv.close()
    with open(cache_path, 'rb') as fh:
        assert fh.read(15) == b"SQLite format 3"
