# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Provide basic caching services to avoid extraneous queries over
multiple policies on the same resource type.
"""
import pickle  # nosec nosemgrep

from datetime import datetime, timedelta
import os
import logging
import sqlite3

log = logging.getLogger('custodian.cache')

CACHE_NOTIFY = False


def factory(config):

    global CACHE_NOTIFY

    if not config:
        return NullCache(None)

    if not config.cache or not config.cache_period:
        if not CACHE_NOTIFY:
            log.debug("Disabling cache")
            CACHE_NOTIFY = True
        return NullCache(config)
    elif config.cache == 'memory':
        if not CACHE_NOTIFY:
            log.debug("Using in-memory cache")
            CACHE_NOTIFY = True
        return InMemoryCache(config)
    return SqlKvCache(config)


class Cache:

    def __init__(self, config):
        self.config = config

    def load(self):
        return False

    def get(self, key):
        pass

    def save(self, key, data):
        pass

    def size(self):
        return 0

    def close(self):
        pass

    def __enter__(self):
        self.load()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class NullCache(Cache):
    pass


class InMemoryCache(Cache):
    # Running in a temporary environment, so keep as a cache.

    __shared_state = {}

    def __init__(self, config):
        super().__init__(config)
        self.data = self.__shared_state

    def load(self):
        return True

    def get(self, key):
        return self.data.get(encode(key))

    def save(self, key, data):
        self.data[encode(key)] = data

    def size(self):
        return sum(map(len, self.data.values()))


def encode(key):
    return pickle.dumps(key, protocol=pickle.HIGHEST_PROTOCOL)  # nosemgrep


def resolve_path(path):
    return os.path.abspath(
        os.path.expanduser(
            os.path.expandvars(path)))


class SqlKvCache(Cache):

    create_table = """
    create table if not exists c7n_cache (
        key blob primary key,
        value blob,
        create_date timestamp
    )
    """

    def __init__(self, config):
        super().__init__(config)
        self.cache_period = config.cache_period
        self.cache_path = resolve_path(config.cache)
        self.conn = None

    def init(self):
        # migration from pickle cache file
        if os.path.exists(self.cache_path):
            with open(self.cache_path, 'rb') as fh:
                header = fh.read(15)
                if header != b'SQLite format 3':
                    log.debug('removing old cache file')
                    os.remove(self.cache_path)
        elif not os.path.exists(os.path.dirname(self.cache_path)):
            # parent directory creation
            os.makedirs(os.path.dirname(self.cache_path))
        self.conn = sqlite3.connect(self.cache_path)
        self.conn.execute(self.create_table)
        with self.conn as cursor:
            result = cursor.execute(
                'delete from c7n_cache where create_date < ?',
                [datetime.utcnow() - timedelta(minutes=self.cache_period)])
            if result.rowcount:
                log.debug('expired %d stale cache entries', result.rowcount)

    def load(self):
        if not self.conn:
            self.init()
        return True

    def get(self, key):
        with self.conn as cursor:
            r = cursor.execute(
                'select value, create_date from c7n_cache where key = ?',
                [sqlite3.Binary(encode(key))]
            )
            row = r.fetchone()
            if row is None:
                return None
            value, create_date = row
            create_date = sqlite3.converters['TIMESTAMP'](create_date.encode('utf8'))
            if (datetime.utcnow() - create_date).total_seconds() / 60.0 > self.cache_period:
                return None
            return pickle.loads(value)  # nosec nosemgrep

    def save(self, key, data, timestamp=None):
        with self.conn as cursor:
            timestamp = timestamp or datetime.utcnow()
            cursor.execute(
                'replace into c7n_cache (key, value, create_date) values (?, ?, ?)',
                (sqlite3.Binary(encode(key)), sqlite3.Binary(encode(data)), timestamp))

    def size(self):
        return os.path.exists(self.cache_path) and os.path.getsize(self.cache_path) or 0

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
