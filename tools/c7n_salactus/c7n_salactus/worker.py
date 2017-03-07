# Copyright 2016 Capital One Services, LLC
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
from contextlib import contextmanager
from datetime import datetime, timedelta
import logging
import itertools
import math
import os
import string
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
from botocore.exceptions import ClientError, ConnectionError

from c7n.credentials import assumed_session
from c7n.resources.s3 import EncryptExtantKeys
from c7n.utils import chunks

# We use a connection cache for sts role assumption
CONN_CACHE = threading.local()

SESSION_NAME = os.environ.get("SALACTUS_NAME", "s3-salactus")
REDIS_HOST = os.environ["SALACTUS_REDIS"]

# Minimum size of the bucket before partitioning
PARTITION_BUCKET_SIZE_THRESHOLD = 100000
#PARTITION_BUCKET_SIZE_THRESHOLD = 20000

# Page size for keys found during partition
PARTITION_KEYSET_THRESHOLD = 500

# Length of partition queue before going parallel
PARTITION_QUEUE_THRESHOLD = 6

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
    'report-only': os.environ.get('SALACTUS_ENCRYPT') and False or True,
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
    ctx = func.delay.func_closure[-1].cell_contents
    q = Queue(ctx.queue, connection=connection)
    argv = list(args)
    argv.append(None)
    job = Job.create(
        func, args=argv, connection=connection,
        description="bucket-%s" % func.func_name,
        origin=q.name, status=JobStatus.QUEUED, timeout=None,
        result_ttl=500, ttl=ctx.ttl)

    for n in chunks(nargs, 100):
        job.created_at = datetime.utcnow()
        with connection.pipeline() as pipe:
            for s in n:
                argv[-1] = s
                job._id = unicode(uuid4())
                job.args = argv
                q.enqueue_job(job, pipeline=pipe)


@contextmanager
def bucket_ops(account_info, bucket_name, api=""):
    """Context manager for dealing with s3 errors in one place
    """
    try:
        yield 42
    except ClientError as e:
        code = e.response['Error']['Code']
        log.info(
            "bucket error account:%s bucket:%s error:%s",
            account_info['name'],
            bucket_name,
            e.response['Error']['Code'])
        if code == "NoSuchBucket":
            pass
        elif code == 'AccessDenied':
            connection.sadd(
                'buckets-denied',
                bucket_id(account_info, bucket_name))
        else:
            connection.hset(
                'buckets-unknown-errors',
                bucket_id(account_info, bucket_name),
                "%s:%s" % (api, e.response['Error']['Code']))
    except:
        # Let the error queue catch it
        raise


def page_strip(page, bucket):
    """Remove bits in content results to minimize memory utilization.

    TODO: evolve this to a key filter on metadata.
    """
    page.pop('ResponseMetadata', None)
    contents_key = bucket['versioned'] and 'Versions' or 'Contents'
    contents = page.get(contents_key, ())
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
        Period=60*60*24,
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
    account_buckets = account_info.pop('buckets', None)
    buckets = [n['Name'] for n in buckets
               if not account_buckets or
               n['Name'] in account_buckets]
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
        with bucket_ops(account_info, b):
            info = {'name': b}
            location = client.get_bucket_location(
                Bucket=b).get('LocationConstraint')
            if location is None:
                region = "us-east-1"
            elif location == 'EU':
                region = "eu-west-1"
            else:
                region = location
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
            versioning = s3.get_bucket_versioning(Bucket=b)
            info['versioned'] = (
                versioning and versioning.get('Status', '')
                in ('Enabled', 'Suspended') or False)
            info['keycount'] = bucket_key_count(cw, info)
            connection.hset('bucket-size', bid, info['keycount'])
            log.info("processing bucket %s", info)
            connection.hset(
                'buckets-start',
                bucket_id(account_info, info['name']), time.time())
            if info['keycount'] > PARTITION_BUCKET_SIZE_THRESHOLD:
                invoke(process_bucket_partitions, account_info, info)
            else:
                invoke(process_bucket_iterator, account_info, info)


class CharSet(object):
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
            cls.hex_lower,
            cls.hex,
            cls.digits,
            cls.ascii_lower,
            cls.ascii_letters,
            cls.ascii_lower_digits,
            cls.ascii_alphanum]


class Strategy(object):
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
        prefix_queue.extend([p['Prefix'] for p in results.get('CommonPrefixes', [])])

    def is_depth_exceeded(self, prefix):
        return prefix.count(self.partition) > self.limit


def get_partition_strategy(account_info, bucket, strategy=None):
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
                bid, "".join(chars)), "\n".join(sorted(keys)))

    for n, sset in normalized.items():
        charset = charset.symmetric_difference(sset)

    return charset


def detect_partition_strategy(account_info, bucket, delimiters=('/', '-'), prefix=''):
    """Try to detect the best partitioning strategy for a large bucket

    Consider nested buckets with common prefixes, and flat buckets.
    """
    bid = bucket_id(account_info, bucket['name'])
    session = get_session(account_info)
    s3 = session.client('s3', region_name=bucket['region'], config=s3config)

    (contents_key,
     contents_method,
     continue_tokens) = BUCKET_OBJ_DESC[bucket['versioned']]

    with bucket_ops(account_info, bucket['name'], 'detect'):
        keys = set()
        for delimiter in delimiters:
            method = getattr(s3, contents_method, None)
            results = method(
                Bucket=bucket['name'], Prefix=prefix, Delimiter=delimiter)
            prefixes = [p['Prefix'] for p in results.get('CommonPrefixes', [])]
            contents = results.get(contents_key, [])
            keys.update([k['Key'] for k in contents])
            # If we have common prefixes within limit thresholds go wide
            if (len(prefixes) > 0 and
                len(prefixes) < 1000 and
                    len(contents) < 1000):
                log.info("%s detected common prefix delimiter:%s contents:%d common:%d",
                         bid, delimiter, len(contents), len(prefixes))
                limit = prefix and 2 or 4
                return process_bucket_partitions(
                    account_info, bucket, partition=delimiter,
                    strategy='p', prefix_set=prefixes, limit=limit)

    # Detect character sets
    charset = get_keys_charset(keys, bid)
    log.info("Detected charset %s for %s", charset, bid)

    # Determine the depth we need to keep total api calls below threshold
    scan_count = bucket['keycount'] / 1000.0
    for limit in range(1, 4):
        if math.pow(len(charset), limit) * 1000 > scan_count:
            break

    # Dispatch
    prefixes = ('',)
    prefixes = NGramPartition(
        charset, limit=limit).initialize_prefixes(prefixes)

    # Pregen on ngram means we have many potentially useless prefixes
    # todo carry charset forward as param, and go incremental on prefix
    # ngram expansion
    connection.hincrby('bucket-partition', bid, len(prefixes))
    return bulk_invoke(
        process_bucket_iterator, [account_info, bucket], prefixes)


@job('bucket-partition', timeout=3600*12, connection=connection)
def process_bucket_partitions(
        account_info, bucket, prefix_set=('',), partition='/',
        strategy=None, limit=4):
    """Split up a bucket keyspace into smaller sets for parallel iteration.
    """

    if strategy is None:
        return detect_partition_strategy(account_info, bucket)
    strategy = get_partition_strategy(account_info, bucket, strategy)
    strategy.limit = limit
    strategy.partition = partition
    (contents_key,
     contents_method,
     continue_tokens) = BUCKET_OBJ_DESC[bucket['versioned']]
    prefix_queue = strategy.initialize_prefixes(prefix_set)

    keyset = []
    bid = bucket_id(account_info, bucket['name'])
    log.info("Process partition bid:%s strategy:%s delimiter:%s queue:%d limit:%d",
             bid, strategy.__class__.__name__[0], partition, len(prefix_queue), limit)
    session = get_session(account_info)
    s3 = session.client('s3', region_name=bucket['region'], config=s3config)

    def statm(prefix):
        return "keyset:%d queue:%d prefix:%s bucket:%s size:%d" % (
            len(keyset), len(prefix_queue), prefix, bid, bucket['keycount'])

    while prefix_queue:
        connection.hincrby('bucket-partition', bid, 1)
        prefix = prefix_queue.pop()
        if strategy.is_depth_exceeded(prefix):
            log.info("Partition max depth reached, %s", statm(prefix))
            invoke(process_bucket_iterator, account_info, bucket, prefix)
            continue
        method = getattr(s3, contents_method, None)
        results = page_strip(method(
            Bucket=bucket['name'], Prefix=prefix, Delimiter=partition),
            bucket)
        keyset.extend(results.get(contents_key, ()))

        # As we probe we find keys, process any found
        if len(keyset) > PARTITION_KEYSET_THRESHOLD:
            log.info("Partition, processing keyset %s", statm(prefix))
            invoke(
                process_keyset, account_info, bucket,
                page_strip({contents_key: keyset}, bucket))
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
                return detect_partition_strategy(account_info, bucket, prefix=prefix)

            invoke(process_bucket_iterator,
                   account_info, bucket, prefix, delimiter=partition,
                   **continuation_params)

        # If the queue get too deep, then go parallel
        if len(prefix_queue) > PARTITION_QUEUE_THRESHOLD:
            log.info("Partition add friends, %s", statm(prefix))
            for s_prefix_set in chunks(
                    prefix_queue[PARTITION_QUEUE_THRESHOLD-1:],
                    PARTITION_QUEUE_THRESHOLD-1):

                for s in list(s_prefix_set):
                    if strategy.is_depth_exceeded(prefix):
                        invoke(process_bucket_iterator,
                               account_info, bucket, s)
                        s_prefix_set.remove(s)

                if not s_prefix_set:
                    continue
                invoke(process_bucket_partitions,
                       account_info, bucket,
                       prefix_set=s_prefix_set, partition=partition,
                       strategy=strategy, limit=limit)
            prefix_queue = prefix_queue[:PARTITION_QUEUE_THRESHOLD-1]

    if keyset:
        invoke(process_keyset, account_info, bucket, {contents_key: keyset})


@job('bucket-page-iterator', timeout=3600*24, connection=connection)
def process_bucket_iterator(account_info, bucket,
                            prefix="", delimiter="", **continuation):
    """Bucket pagination
    """
    log.info("Iterating keys bucket %s prefix %s delimiter %s",
             bucket_id(account_info, bucket['name']), prefix, delimiter)
    session = get_session(account_info)
    s3 = session.client('s3', region_name=bucket['region'], config=s3config)

    (contents_key,
     contents_method,
     _) = BUCKET_OBJ_DESC[bucket['versioned']]

    params = dict(Bucket=bucket['name'], Prefix=prefix)
    if delimiter:
        params['Delimiter'] = delimiter
    if continuation:
        params.update({k[4:]: v for k, v in continuation.items()})
    paginator = s3.get_paginator(contents_method).paginate(**params)
    with bucket_ops(account_info, bucket['name'], 'page'):
        for page in paginator:
            page = page_strip(page, bucket)
            if page.get(contents_key):
                invoke(process_keyset, account_info, bucket, page)


@job('bucket-keyset-scan', timeout=3600*12, connection=connection)
def process_keyset(account_info, bucket, key_set):
    session = get_session(account_info)
    s3 = session.client('s3', region_name=bucket['region'], config=s3config)
    processor = EncryptExtantKeys(keyconfig)
    remediation_count = 0
    denied_count = 0
    contents_key, _, _ = BUCKET_OBJ_DESC[bucket['versioned']]
    processor = (bucket['versioned'] and processor.process_version
                 or processor.process_key)
    connection.hincrby(
        'keys-scanned', bucket_id(account_info, bucket['name']),
        len(key_set.get(contents_key, [])))
    log.info("processing page size: %d on %s",
             len(key_set.get(contents_key, ())),
             bucket_id(account_info, bucket['name']))

    with bucket_ops(account_info, bucket, 'key'):
        for k in key_set.get(contents_key, []):
            try:
                result = processor(s3, bucket_name=bucket['name'], key=k)
            except ConnectionError:
                continue
            except ClientError as e:
                #  https://goo.gl/HZLv9b
                code = e.response['Error']['Code']
                if code == '403':  # Permission Denied
                    denied_count += 1
                    continue
                elif code == '404':  # Not Found
                    continue
                elif code in ('503', '400'):  # Slow Down, or token err
                    # TODO, consider backoff alg usage, and re-queue of keys
                    time.sleep(3)
                    continue
                raise
            if result is False:
                continue
            remediation_count += 1
        if remediation_count:
            connection.hincrby(
                'keys-matched',
                bucket_id(account_info, bucket['name']),
                remediation_count)
        if denied_count:
            connection.hincrby(
                'keys-denied',
                bucket_id(account_info, bucket['name']),
                denied_count)
