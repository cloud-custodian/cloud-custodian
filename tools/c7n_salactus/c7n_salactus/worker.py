# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Salactus, eater of s3 buckets.

queues:
 - buckets-iterator
 - bucket-set
 - bucket-partition
 - bucket-page-iterator
 - bucket-keyset-scan

stats:
 - buckets-complete:set
 - buckets-start:hash
 - buckets-end:hash

 - buckets-size: hash
 - buckets-large: hash # TODO

 - keys-scanned:hash
 - keys-matched:hash
 - keys-denied:hash

monitor:
 - buckets-unknown-errors:hash
 - buckets-denied:set

"""
import collections
from contextlib import contextmanager
from datetime import datetime, timedelta
import gc
import itertools
import json
import logging
import math
import os
import random
import string
import sys
import threading
import time
from uuid import uuid4

import redis
from rq.decorators import job
# for bulk invoke impl
from rq.queue import Queue
from rq.job import JobStatus, Job

import boto3
from botocore.client import Config
from botocore.exceptions import (
    ClientError, ConnectionError, EndpointConnectionError)

from concurrent.futures import ThreadPoolExecutor, as_completed

from c7n.credentials import assumed_session
from c7n.resources.s3 import EncryptExtantKeys
from c7n.utils import chunks, dumps

from c7n_salactus.objectacl import ObjectAclCheck
from c7n_salactus.inventory import load_bucket_inventory, get_bucket_inventory


def patch_ssl():
    if getattr(CONN_CACHE, 'patched', None):
        return
    from botocore.vendored import requests
    # Pick a preferred cipher suite, needs some benchmarking.
    # https://www.slideshare.net/AmazonWebServices/maximizing-amazon-s3-performance-stg304-aws-reinvent-2013
    requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = ':AES128-GCM-SHA256'
    try:
        setattr(requests.packages.urllib3.contrib.pyopenssl,
                'DEFAULT_SSL_CIPHER_LIST',
                ':AES128-GCM-SHA256')
    except AttributeError:
        # no pyopenssl support used / needed / available
        pass
    setattr(CONN_CACHE, 'patched', True)


# We use a connection cache for sts role assumption
CONN_CACHE = threading.local()

SESSION_NAME = os.environ.get("SALACTUS_NAME", "s3-salactus")
REDIS_HOST = os.environ["SALACTUS_REDIS"]

# Minimum size of the bucket before partitioning
PARTITION_BUCKET_SIZE_THRESHOLD = 100000

# Page size for keys found during partition
PARTITION_KEYSET_THRESHOLD = 500

# Length of partition queue before going parallel
PARTITION_QUEUE_THRESHOLD = 6

DEFAULT_TTL = 60 * 60 * 48

# Default size of the bucket before checking for inventory
DEFAULT_INVENTORY_BUCKET_SIZE_THRESHOLD = \
    int(os.environ.get("SALACTUS_INVENTORY_THRESHOLD", 100000))

BUCKET_OBJ_DESC = {
    True: ('Versions', 'list_object_versions',
           ('NextKeyMarker', 'NextVersionIdMarker')),
    False: ('Contents', 'list_objects_v2',
            ('NextContinuationToken',))
}

connection = redis.Redis(host=REDIS_HOST)
# Increase timeouts to assist with non local regions, also
# seeing some odd net slowness all around.
s3config = Config(read_timeout=420, connect_timeout=90)
keyconfig = {
    'report-only': not os.environ.get('SALACTUS_ENCRYPT') and True or False,
    'glacier': False,
    'large': True,
    'key-id': os.environ.get('SALACTUS_KEYID'),
    'crypto': os.environ.get('SALACTUS_CRYPTO', 'AES256')}

log = logging.getLogger("salactus")


def get_session(account_info):
    """Get a boto3 sesssion potentially cross account sts assumed

    assumed sessions are automatically refreshed.
    """
    s = getattr(CONN_CACHE, '%s-session' % account_info['name'], None)
    if s is not None:
        return s
    if account_info.get('role'):
        s = assumed_session(account_info['role'], SESSION_NAME)
    else:
        s = boto3.Session()
    setattr(CONN_CACHE, '%s-session' % account_info['name'], s)
    return s


def bucket_id(account_info, bucket_name):
    return "%s:%s" % (account_info['name'], bucket_name)


def invoke(func, *args, **kw):
    func.delay(*args, **kw)


def bulk_invoke(func, args, nargs):
    """Bulk invoke a function via queues

    Uses internal implementation details of rq.
    """
    # for comparison, simplest thing that works
    # for i in nargs:
    #    argv = list(args)
    #    argv.append(i)
    #    func.delay(*argv)

    # some variances between cpy and pypy, sniff detect
    for closure in func.delay.func_closure:
        if getattr(closure.cell_contents, 'queue', None):
            ctx = closure.cell_contents
            break
    q = Queue(ctx.queue, connection=connection)
    argv = list(args)
    argv.append(None)
    job = Job.create(
        func, args=argv, connection=connection,
        description="bucket-%s" % func.func_name,
        origin=q.name, status=JobStatus.QUEUED, timeout=ctx.timeout,
        result_ttl=0, ttl=ctx.ttl)

    for n in chunks(nargs, 100):
        job.created_at = datetime.utcnow()
        with connection.pipeline() as pipe:
            for s in n:
                argv[-1] = s
                job._id = unicode(uuid4())  # noqa: F821
                job.args = argv
                q.enqueue_job(job, pipeline=pipe)
            pipe.execute()


@contextmanager
def bucket_ops(bid, api=""):
    """Context manager for dealing with s3 errors in one place

    bid: bucket_id in form of account_name:bucket_name
    """
    try:
        yield 42
    except ClientError as e:
        code = e.response['Error']['Code']
        log.info(
            "bucket error bucket:%s error:%s",
            bid,
            e.response['Error']['Code'])
        if code == "NoSuchBucket":
            pass
        elif code == 'AccessDenied':
            connection.sadd('buckets-denied', bid)
        else:
            connection.hset(
                'buckets-unknown-errors',
                bid,
                "%s:%s" % (api, e.response['Error']['Code']))
    except Exception as e:
        connection.hset(
            'buckets-unknown-errors',
            bid,
            "%s:%s" % (api, str(e)))
        # Let the error queue catch it
        raise


def page_strip(page, versioned):
    """Remove bits in content results to minimize memory utilization.

    TODO: evolve this to a key filter on metadata, like date

    """
    # page strip filtering should be conditional
    page.pop('ResponseMetadata', None)
    contents_key = versioned and 'Versions' or 'Contents'
    contents = page.get(contents_key, ())

    # aggressive size
    if versioned:
        keys = []
        for k in contents:
            if k['IsLatest']:
                keys.append((k['Key'], k['VersionId'], True))
            else:
                keys.append((k['Key'], k['VersionId']))
        return keys
    else:
        return [k['Key'] for k in contents]

    if not contents:
        return page

    # Depending on use case we may want these
    for k in contents:
        k.pop('Owner', None)
        k.pop('LastModified', None)
        k.pop('ETag', None)
        k.pop('StorageClass', None)
        k.pop('Size', None)

    return page


def bucket_key_count(client, bucket):
    params = dict(
        Namespace='AWS/S3',
        MetricName='NumberOfObjects',
        Dimensions=[
            {'Name': 'BucketName',
             'Value': bucket['name']},
            {'Name': 'StorageType',
             'Value': 'AllStorageTypes'}],
        StartTime=datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0) - timedelta(1),
        EndTime=datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0),
        Period=60 * 60 * 24,
        Statistics=['Minimum'])
    response = client.get_metric_statistics(**params)
    if not response['Datapoints']:
        return 0
    return response['Datapoints'][0]['Minimum']


@job('buckets-iterator', timeout=3600, connection=connection)
def process_account(account_info):
    """Scan all buckets in an account and schedule processing"""
    log = logging.getLogger('salactus.bucket-iterator')
    log.info("processing account %s", account_info)
    session = get_session(account_info)
    client = session.client('s3', config=s3config)
    buckets = client.list_buckets()['Buckets']

    connection.hset(
        'bucket-accounts', account_info['name'], json.dumps(account_info))

    for b in buckets:
        connection.hset(
            'bucket-ages', bucket_id(account_info, b['Name']),
            b['CreationDate'].isoformat())

    account_buckets = account_info.pop('buckets', None)
    buckets = [n['Name'] for n in buckets
               if not account_buckets or
               n['Name'] in account_buckets]
    account_not_buckets = account_info.pop('not-buckets', None)
    buckets = [n for n in buckets
               if not account_not_buckets or
               n not in account_not_buckets]
    log.info("processing %d buckets in account %s",
             len(buckets), account_info['name'])
    for bucket_set in chunks(buckets, 50):
        invoke(process_bucket_set, account_info, bucket_set)


@job('bucket-set', timeout=3600, connection=connection)
def process_bucket_set(account_info, buckets):
    """Process a collection of buckets.

    For each bucket fetch location, versioning and size and
    then kickoff processing strategy based on size.
    """
    region_clients = {}
    log = logging.getLogger('salactus.bucket-set')
    log.info("processing account %s", account_info)
    session = get_session(account_info)
    client = session.client('s3', config=s3config)

    for b in buckets:
        bid = bucket_id(account_info, b)
        with bucket_ops(bid):
            info = {'name': b}
            error = None

            try:
                location = client.get_bucket_location(
                    Bucket=b).get('LocationConstraint')
            except Exception as e:
                error = e
                location = None

            if location is None:
                region = "us-east-1"
            elif location == 'EU':
                region = "eu-west-1"
            else:
                region = location

            if (account_info.get('regions', ()) and
                    region not in account_info.get('regions', ())):
                continue

            info['region'] = region
            if region not in region_clients:
                region_clients.setdefault(region, {})
                region_clients[region]['s3'] = s3 = session.client(
                    's3', region_name=region, config=s3config)
                region_clients[region]['cloudwatch'] = cw = session.client(
                    'cloudwatch', region_name=region, config=s3config)
            else:
                s3 = region_clients[region]['s3']
                cw = region_clients[region]['cloudwatch']

            try:
                info['keycount'] = bucket_key_count(cw, info)
            except Exception:
                raise
            else:
                connection.hset('bucket-sizes', bid, info['keycount'])

            if error:
                raise error

            connection.hset('bucket-regions', bid, region)

            versioning = s3.get_bucket_versioning(Bucket=b)
            info['versioned'] = (
                versioning and versioning.get('Status', '')
                in ('Enabled', 'Suspended') or False)
            connection.hset('bucket-versions', bid, int(info['versioned']))

            log.info("processing bucket %s", info)
            connection.hset('bucket-starts', bid, time.time())
            dispatch_object_source(s3, account_info, bid, info)


def dispatch_object_source(client, account_info, bid, bucket_info):
    """Select and dispatch an object source for a bucket.

    Choices are bucket partition, inventory, or direct pagination.
    """

    if (account_info.get('inventory') and
        bucket_info['keycount'] >
            account_info['inventory'].get('bucket-size-threshold',
                                          DEFAULT_INVENTORY_BUCKET_SIZE_THRESHOLD)):
        inventory_info = get_bucket_inventory(
            client,
            bucket_info['name'],
            account_info['inventory'].get('id-selector', '*'))
        if inventory_info is not None:
            return invoke(
                process_bucket_inventory, bid,
                inventory_info['bucket'], inventory_info['prefix'])

    if bucket_info['keycount'] > PARTITION_BUCKET_SIZE_THRESHOLD:
        invoke(process_bucket_partitions, bid)
    else:
        invoke(process_bucket_iterator, bid)


class CharSet:
    """Sets of character/gram populations for the ngram partition strategy.
    """
    hex_lower = set(string.hexdigits.lower())
    hex = set(string.hexdigits)
    digits = set(string.digits)
    ascii_lower = set(string.ascii_lowercase)
    ascii_letters = set(string.ascii_letters)
    ascii_lower_digits = set(string.ascii_lowercase + string.digits)
    ascii_alphanum = set(string.ascii_letters + string.digits)
    punctuation = set(string.punctuation)

    @classmethod
    def charsets(cls):
        return [
            cls.hex,
            cls.hex_lower,
            cls.digits,
            cls.ascii_lower,
            cls.ascii_letters,
            cls.ascii_lower_digits,
            cls.ascii_alphanum]


class Strategy:
    """ Partitioning strategy for an s3 bucket.
    """


class NGramPartition(Strategy):
    """A keyspace partition strategy that uses a fixed set of prefixes.

    Good for flat, shallow keyspaces.
    """

    name = "ngram"

    def __init__(self, grams=set(string.hexdigits.lower()), limit=3):
        self.grams = grams
        self.limit = limit

    def initialize_prefixes(self, prefix_queue):
        if prefix_queue != ('',):
            return prefix_queue
        return ["".join(n) for n in
                itertools.permutations(self.grams, self.limit)]

    def find_partitions(self, prefix_queue, results):
        return []

    def is_depth_execeeded(self, prefix):
        return False


class CommonPrefixPartition(Strategy):
    """A keyspace partition strategy that probes common prefixes.

    We probe a bucket looking for common prefixes up to our max
    partition depth, and use parallel objects iterators on each that
    exceed the max depth or that have more than 1k keys.

    Note common prefixes are limited to a thousand by default, if that happens
    we should record an error.
    """

    name = "common-prefix"

    def __init__(self, partition='/', limit=4):
        self.partition = partition
        self.limit = limit

    def initialize_prefixes(self, prefix_queue):
        if prefix_queue == ('',):
            return ['']
        return prefix_queue

    def find_partitions(self, prefix_queue, results):
        prefix_queue.extend(
            [p['Prefix'] for p in results.get('CommonPrefixes', [])])

    def is_depth_exceeded(self, prefix):
        return prefix.count(self.partition) > self.limit


def get_partition_strategy(strategy):
    if strategy == 'p':
        return CommonPrefixPartition()
    elif strategy == 'n':
        return NGramPartition()
    elif isinstance(strategy, Strategy):
        return strategy
    raise ValueError("Invalid partition strategy %s" % strategy)


def get_keys_charset(keys, bid):
    """ Use set of keys as selector for character superset

    Note this isn't optimal, its probabilistic on the keyset char population.
    """
    # use the keys found to sample possible chars
    chars = set()
    for k in keys:
        chars.update(k[:4])
    remainder = chars

    # Normalize charsets for matching
    normalized = {}
    for n, sset in [
        ("p", set(string.punctuation)),
        ("w", set(string.whitespace))
    ]:
        m = chars.intersection(sset)
        if m:
            normalized[n] = m
            remainder = remainder.difference(sset)

    # Detect character sets
    charset = None
    for candidate in CharSet.charsets():
        if remainder.issubset(candidate):
            charset = candidate
            break

    if charset is None:
        raise ValueError(
            "Bucket: %s Failed charset ngram detection %r\n%s" % (
                bid, "".join(chars), "\n".join(sorted(keys))))

    for n, sset in normalized.items():
        charset = charset.symmetric_difference(sset)

    return charset


def detect_partition_strategy(bid, delimiters=('/', '-'), prefix=''):
    """Try to detect the best partitioning strategy for a large bucket

    Consider nested buckets with common prefixes, and flat buckets.
    """
    account, bucket = bid.split(":", 1)
    region = connection.hget('bucket-regions', bid)
    versioned = bool(int(connection.hget('bucket-versions', bid)))
    size = int(float(connection.hget('bucket-sizes', bid)))
    session = get_session(
        json.loads(connection.hget('bucket-accounts', account)))
    s3 = session.client('s3', region_name=region, config=s3config)

    (contents_key,
     contents_method,
     _) = BUCKET_OBJ_DESC[versioned]

    with bucket_ops(bid, 'detect'):
        keys = set()
        for delimiter in delimiters:
            method = getattr(s3, contents_method, None)
            results = method(
                Bucket=bucket, Prefix=prefix, Delimiter=delimiter)
            prefixes = [p['Prefix'] for p in results.get('CommonPrefixes', [])]
            contents = results.get(contents_key, [])
            keys.update([k['Key'] for k in contents])
            # If we have common prefixes within limit thresholds go wide
            if (len(prefixes) > 0 and
                len(prefixes) < 1000 and
                    len(contents) < 1000):
                log.info(
                    "%s detected prefix delimiter:%s contents:%d prefixes:%d",
                    bid, delimiter, len(contents), len(prefixes))
                limit = prefix and 2 or 4
                return process_bucket_partitions(
                    bid, partition=delimiter,
                    strategy='p', prefix_set=prefixes, limit=limit)

    # Detect character sets
    charset = get_keys_charset(keys, bid)
    log.info("Detected charset %s for %s", charset, bid)

    # Determine the depth we need to keep total api calls below threshold
    scan_count = size / 1000.0
    for limit in range(1, 4):
        if math.pow(len(charset), limit) * 1000 > scan_count:
            break

    # Dispatch
    prefixes = ('',)
    prefixes = NGramPartition(
        charset, limit=limit).initialize_prefixes(prefixes)

    #
    random.shuffle(prefixes)

    # Pregen on ngram means we have many potentially useless prefixes
    # todo carry charset forward as param, and go incremental on prefix
    # ngram expansion
    connection.hincrby('bucket-partition', bid, len(prefixes))
    return bulk_invoke(
        process_bucket_iterator, [bid], prefixes)


@job('bucket-partition', timeout=3600 * 4, ttl=DEFAULT_TTL,
     connection=connection, result_ttl=0)
def process_bucket_partitions(
        bid, prefix_set=('',), partition='/', strategy=None, limit=4):
    """Split up a bucket keyspace into smaller sets for parallel iteration.
    """
    if strategy is None:
        return detect_partition_strategy(bid)

    account, bucket = bid.split(':', 1)
    region = connection.hget('bucket-regions', bid)
    versioned = bool(int(connection.hget('bucket-versions', bid)))
    session = get_session(
        json.loads(connection.hget('bucket-accounts', account)))
    size = int(float(connection.hget('bucket-sizes', bid)))
    s3 = session.client('s3', region_name=region, config=s3config)

    strategy = get_partition_strategy(strategy)
    strategy.limit = limit
    strategy.partition = partition
    (contents_key,
     contents_method,
     continue_tokens) = BUCKET_OBJ_DESC[versioned]
    prefix_queue = strategy.initialize_prefixes(prefix_set)

    keyset = []
    log.info(
        "Process partition bid:%s strategy:%s delimiter:%s queue:%d limit:%d",
        bid, strategy.__class__.__name__[0], partition,
        len(prefix_queue), limit)

    def statm(prefix):
        return "keyset:%d queue:%d prefix:%s bucket:%s size:%d" % (
            len(keyset), len(prefix_queue), prefix, bid, size)

    while prefix_queue:
        connection.hincrby('bucket-partition', bid, 1)
        prefix = prefix_queue.pop()
        if strategy.is_depth_exceeded(prefix):
            log.info("Partition max depth reached, %s", statm(prefix))
            invoke(process_bucket_iterator, bid, prefix)
            continue
        method = getattr(s3, contents_method, None)
        results = method(Bucket=bucket, Prefix=prefix, Delimiter=partition)
        keyset.extend(results.get(contents_key, ()))

        # As we probe we find keys, process any found
        if len(keyset) > PARTITION_KEYSET_THRESHOLD:
            log.info("Partition, processing keyset %s", statm(prefix))
            page = page_strip({contents_key: keyset}, versioned)
            if page:
                invoke(process_keyset, bid, page)
            keyset = []

        strategy.find_partitions(prefix_queue, results)

        # Do we have more than 1k keys at this level, continue iteration
        continuation_params = {
            k: results[k] for k in continue_tokens if k in results}
        if continuation_params:
            bp = int(connection.hget('bucket-partition', bid))
            log.info("Partition has 1k keys, %s %s", statm(prefix), bp)
            if not prefix_queue and bp < 5:
                log.info("Recursive detection")
                return detect_partition_strategy(bid, prefix=prefix)

            invoke(process_bucket_iterator, bid, prefix, delimiter=partition,
                   **continuation_params)

        # If the queue get too deep, then go parallel
        if len(prefix_queue) > PARTITION_QUEUE_THRESHOLD:
            log.info("Partition add friends, %s", statm(prefix))
            for s_prefix_set in chunks(
                    prefix_queue[PARTITION_QUEUE_THRESHOLD - 1:],
                    PARTITION_QUEUE_THRESHOLD - 1):

                for s in list(s_prefix_set):
                    if strategy.is_depth_exceeded(prefix):
                        invoke(process_bucket_iterator, bid, s)
                        s_prefix_set.remove(s)

                if not s_prefix_set:
                    continue
                invoke(process_bucket_partitions,
                       bid,
                       prefix_set=s_prefix_set, partition=partition,
                       strategy=strategy, limit=limit)
            prefix_queue = prefix_queue[:PARTITION_QUEUE_THRESHOLD - 1]

    if keyset:
        page = page_strip({contents_key: keyset}, versioned)
        if page:
            invoke(process_keyset, bid, page)


@job('bucket-inventory', timeout=DEFAULT_TTL, ttl=DEFAULT_TTL,
     connection=connection, result_ttl=0)
def process_bucket_inventory(bid, inventory_bucket, inventory_prefix):
    """Load last inventory dump and feed as key source.
    """
    log.info("Loading bucket %s keys from inventory s3://%s/%s",
             bid, inventory_bucket, inventory_prefix)
    account, _ = bid.split(':', 1)
    region = connection.hget('bucket-regions', bid)
    versioned = bool(int(connection.hget('bucket-versions', bid)))
    session = boto3.Session()
    s3 = session.client('s3', region_name=region, config=s3config)

    # find any key visitors with inventory filtering
    account_info = json.loads(connection.hget('bucket-accounts', account))
    ifilters = [v.inventory_filter for v
                in get_key_visitors(account_info) if v.inventory_filter]

    with bucket_ops(bid, 'inventory'):
        page_iterator = load_bucket_inventory(
            s3, inventory_bucket, inventory_prefix, versioned, ifilters)
        if page_iterator is None:
            log.info("bucket:%s could not find inventory" % bid)
            # case: inventory configured but not delivered yet
            # action: dispatch to bucket partition (assumes 100k+ for inventory)
            # - todo consider max inventory age/staleness for usage
            return invoke(process_bucket_partitions, bid)
        connection.hset('buckets-inventory', bid, 1)
        for page in page_iterator:
            invoke(process_keyset, bid, page)


@job('bucket-page-iterator', timeout=DEFAULT_TTL, ttl=DEFAULT_TTL,
     connection=connection, result_ttl=0)
def process_bucket_iterator(bid, prefix="", delimiter="", **continuation):
    """Bucket pagination
    """
    log.info("Iterating keys bucket %s prefix %s delimiter %s",
             bid, prefix, delimiter)

    account, bucket = bid.split(':', 1)
    region = connection.hget('bucket-regions', bid)
    versioned = bool(int(connection.hget('bucket-versions', bid)))
    session = get_session(
        json.loads(connection.hget('bucket-accounts', account)))
    s3 = session.client('s3', region_name=region, config=s3config)

    (_, contents_method, _) = BUCKET_OBJ_DESC[versioned]

    params = dict(Bucket=bucket)
    if prefix:
        params['Prefix'] = prefix
    if delimiter:
        params['Delimiter'] = delimiter
    if continuation:
        params.update({k[4:]: v for k, v in continuation.items()})
    paginator = s3.get_paginator(contents_method).paginate(**params)
    with bucket_ops(bid, 'page'):
        ptime = time.time()
        pcounter = 0
        for page in paginator:
            page = page_strip(page, versioned)
            pcounter += 1
            if page:
                invoke(process_keyset, bid, page)

            if pcounter % 10 == 0:
                with connection.pipeline() as p:
                    nptime = time.time()
                    p.hincrby('bucket-pages', bid, 1)
                    p.hincrby('bucket-pages-time', bid, int(nptime - ptime))
                    ptime = nptime
                    p.execute()

        if pcounter % 10:
            with connection.pipeline() as p:
                nptime = time.time()
                p.hincrby('bucket-pages', bid, 1)
                p.hincrby('bucket-pages-time', bid, int(nptime - ptime))
                p.execute()


def get_key_visitors(account_info):
    if not account_info.get('visitors'):
        return [EncryptExtantKeys(keyconfig)]
    visitors = []
    for v in account_info.get('visitors'):
        if v['type'] == 'encrypt-keys':
            vi = EncryptExtantKeys(v)
            vi.visitor_name = 'encrypt-keys'
            vi.inventory_filter = filter_encrypted
            visitors.append(vi)
        elif v['type'] == 'object-acl':
            vi = ObjectAclCheck(v)
            vi.visitor_name = 'object-acl'
            vi.inventory_filter = None
            visitors.append(vi)
    return visitors


def filter_encrypted(ischema, kr):
    if 'EncryptionStatus' not in ischema:
        return False
    return kr[ischema['EncryptionStatus']].startswith('SSE')


@job('bucket-keyset-scan', timeout=DEFAULT_TTL, ttl=DEFAULT_TTL,
     connection=connection, result_ttl=0)
def process_keyset(bid, key_set):
    account, bucket = bid.split(':', 1)
    region = connection.hget('bucket-regions', bid)
    versioned = bool(int(connection.hget('bucket-versions', bid)))
    account_info = json.loads(connection.hget('bucket-accounts', account))

    visitors = get_key_visitors(account_info)
    object_reporting = account_info.get('object-reporting')
    session = get_session(account_info)

    patch_ssl()
    s3 = session.client('s3', region_name=region, config=s3config)

    error_count = sesserr = connerr = enderr = missing_count = 0
    throttle_count = denied_count = remediation_count = 0
    key_count = len(key_set)
    start_time = time.time()

    objects = {v.visitor_name: [] for v in visitors}
    objects['objects_denied'] = []

    with bucket_ops(bid, 'key'):
        with ThreadPoolExecutor(max_workers=10) as w:
            futures = {}
            for kchunk in chunks(key_set, 100):
                for v in visitors:
                    processor = (versioned and
                        v.process_version or v.process_key)
                    futures[w.submit(
                        process_key_chunk, s3, bucket, kchunk,
                        processor, bool(object_reporting))] = v.visitor_name

            for f in as_completed(futures):
                if f.exception():
                    log.warning("key error: %s", f.exception())
                    error_count += 1
                    continue
                stats = f.result()
                remediation_count += stats['remediated']
                denied_count += stats['denied']
                missing_count += stats['missing']
                throttle_count += stats['throttle']
                sesserr += stats['session']
                enderr += stats['endpoint']
                connerr += stats['connection']
                if object_reporting:
                    vname = futures[f]
                    objects[vname].extend(stats['objects'])
                    objects['objects_denied'].extend(stats['objects_denied'])

        with connection.pipeline() as p:
            if remediation_count:
                p.hincrby('keys-matched', bid, remediation_count)
            if denied_count:
                p.hincrby('keys-denied', bid, denied_count)
            if missing_count:
                p.hincrby('keys-missing', bid, missing_count)
            if throttle_count:
                p.hincrby('keys-throttled', bid, throttle_count)
            if sesserr:
                p.hincrby('keys-sesserr', bid, sesserr)
            if connerr:
                p.hincrby('keys-connerr', bid, connerr)
            if enderr:
                p.hincrby('keys-enderr', bid, enderr)
            if error_count:
                p.hincrby('keys-error', bid, error_count)

            p.hincrby('keys-scanned', bid, key_count)
            # track count again as we reset metrics period
            p.hincrby('keys-count', bid, key_count)
            p.hincrby('keys-time', bid, int(time.time() - start_time))
            p.execute()

    # write out object level info
    if object_reporting:
        publish_object_records(bid, objects, object_reporting)

    # trigger some mem collection
    if getattr(sys, 'pypy_version_info', None):
        gc.collect()


def process_key_chunk(s3, bucket, kchunk, processor, object_reporting):
    stats = collections.defaultdict(lambda: 0)
    if object_reporting:
        stats['objects'] = []
        stats['objects_denied'] = []

    for k in kchunk:
        if isinstance(k, str):
            k = {'Key': k}
        elif isinstance(k, (list, tuple)) and len(k) == 2:
            k = {'Key': k[0], 'VersionId': k[1] or 'null', 'IsLatest': False}
        else:
            k = {'Key': k[0], 'VersionId': k[1] or 'null', 'IsLatest': True}
        try:
            result = processor(s3, bucket_name=bucket, key=k)
        except EndpointConnectionError:
            stats['endpoint'] += 1
        except ConnectionError:
            stats['connection'] += 1
        except ClientError as e:
            #  https://docs.aws.amazon.com/AmazonS3/latest/API/ErrorResponses.html
            code = e.response['Error']['Code']
            if code in ('403', 'AccessDenied', '405', 'MethodNotAllowed'):  # Permission Denied
                stats['denied'] += 1
                if object_reporting:
                    stats['objects_denied'].append(k)
            elif code in ('404', 'NoSuchKey', 'NoSuchVersion'):  # Not Found
                stats['missing'] += 1
            elif code in ('503', '500', 'SlowDown'):  # Slow down, or throttle
                time.sleep(3)
                stats['throttle'] += 1
            elif code in ('400',):  # token err, typically
                time.sleep(3)
                stats['session'] += 1
            else:
                raise
        else:
            if result:
                stats['remediated'] += 1
            if result and object_reporting:
                stats['objects'].append(result)
    return stats


def publish_object_records(bid, objects, reporting):
    found = False
    for k in objects.keys():
        if objects[k]:
            found = True
    if not found:
        return

    client = get_session({'name': 'object-records'}).client('s3')
    bucket = reporting.get('bucket')
    record_prefix = reporting.get('record-prefix')
    key = "%s/%s/%s/%s.json" % (
        reporting.get('prefix').strip('/'),
        record_prefix, bid, str(uuid4()))
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=dumps(objects),
        ACL="bucket-owner-full-control",
        ServerSideEncryption="AES256")
