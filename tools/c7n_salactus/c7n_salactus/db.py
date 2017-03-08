import json
import os
from collections import Counter


from c7n_salactus.worker import connection as conn


class Database(object):

    def __init__(self, path=None):
        if path:
            with open(os.path.expanduser(path)) as fh:
                self.data = json.load(fh)
        else:
            self.data = get_data()

    def accounts(self, accounts=()):
        accounts = {}
        for k in self.data['bucket-size'].keys():
            a, b = k.split(':')
            accounts.setdefault(a, []).append(k)
        return [Account(a, [Bucket(b, self.data) for b in buckets])
                for a, buckets in accounts.items()]

    def buckets(self, accounts=()):
        if accounts:
            return [
                Bucket(k, self.data) for k in self.data['bucket-size'].keys()
                if k.split(":")[0] in accounts]
        return [Bucket(k, self.data) for k in self.data['bucket-size'].keys()]

    def save(self, path):
        with open(os.path.expanduser(path), 'w') as fh:
            json.dump(self.data, fh, indent=2)


def db(dbpath=None):
    return Database(dbpath)


class Account(object):

    __slots__ = ('name', 'buckets')

    def __init__(self, name, buckets):
        self.name = name
        self.buckets = buckets

    @property
    def size(self):
        return sum([b.size for b in self.buckets])

    @property
    def matched(self):
        return sum([b.matched for b in self.buckets])

    @property
    def keys_denied(self):
        return sum([b.keys_denied for b in self.buckets])

    @property
    def scanned(self):
        return sum([b.scanned for b in self.buckets])

    @property
    def percent_scanned(self):
        if self.size == 0:
            return 100.0
        size = self.size - sum([b.size for b in self.buckets if b.denied])
        return min(float(self.scanned) / size * 100.0, 100.0)


class Bucket(object):

    __slots__ = ('bucket_id', 'data')

    def __init__(self, bucket_id, data):
        self.bucket_id = bucket_id
        self.data = data

    @property
    def account(self):
        return self.bucket_id.split(':')[0]

    @property
    def name(self):
        return self.bucket_id.split(":")[1]

    @property
    def size(self):
        return int(self.data['bucket-size'].get(self.bucket_id, 0.0))

    @property
    def matched(self):
        return int(self.data['keys-matched'].get(self.bucket_id, 0.0))

    @property
    def scanned(self):
        return int(self.data['keys-scanned'].get(self.bucket_id, 0.0))

    @property
    def percent_scanned(self):
        if self.size == 0:
            return 100.0
        return min(float(self.scanned) / self.size * 100.0, 100.0)

    @property
    def started(self):
        return self.data['bucket-start'].get(self.bucket_id, 0.0)

    @property
    def partitions(self):
        return int(self.data['bucket-partitions'].get(self.bucket_id, 0.0))

    @property
    def keys_denied(self):
        return int(self.data['keys-denied'].get(self.bucket_id, 0))

    @property
    def denied(self):
        return self.bucket_id in self.data['buckets-denied']

    @property
    def error_count(self):
        return len(self.data['buckets-error'].get(self.bucket_id, ()))


def get_data():
    data = {}
    data['buckets-denied'] = list(
        conn.smembers('buckets-denied'))
    data['buckets-complete'] = list(
        conn.smembers('buckets-complete'))
    data['buckets-start'] = conn.hgetall('buckets-start')
    data['buckets-end'] = conn.hgetall('buckets-end')
    data['bucket-partitions'] = {
        k: int(v) for k, v in conn.hgetall('bucket-partition').items()}
    data['buckets-error'] = conn.hgetall(
        'buckets-unknown-errors')
    data['bucket-size'] = {
        k: float(v) for k, v in conn.hgetall('bucket-size').items()}
    data['keys-scanned'] = {
        k: float(v) for k, v in conn.hgetall('keys-scanned').items()}
    data['keys-matched'] = {
        k: float(v) for k, v in conn.hgetall('keys-matched').items()}
    data['keys-denied'] = {
        k: float(v) for k, v in conn.hgetall('keys-denied').items()}
    return data


def agg(d):
    m = Counter()
    if isinstance(d, (set, list)):
        for v in d:
            l, _ = v.split(":", 1)
            m[l] += 1
        return m
    for k, v in d.items():
        l, _ = k.split(":")
        m[l] += int(v)
        return m
