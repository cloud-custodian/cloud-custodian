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
import argparse
from cStringIO import StringIO
from dateutil.parser import parse
from functools import partial
from gzip import GzipFile
import json
import logging
import math
from multiprocessing import cpu_count, Pool
import os
import tempfile
import time
import sqlite3

import boto3


log = logging.getLogger('c7n_traildb')


def dump(o):
    return json.dumps(o)


def load(s):
    return json.loads(s)


def chunks(iterable, size=50):
    """Break an iterable into lists of size"""
    batch = []
    for n in iterable:
        batch.append(n)
        if len(batch) % size == 0:
            yield batch
            batch = []
    if batch:
        yield batch


def process_trail_set(
        object_set, map_records, reduce_results=None, trail_bucket=None):
    s3 = boto3.Session().client('s3')
    previous = None
    for o in object_set:
        body = s3.get_object(Key=o['Key'], Bucket=trail_bucket)['Body']
        fh = GzipFile(fileobj=StringIO(body.read()))
        data = json.load(fh)
        s = map_records(data['Records'])
        if reduce_results:
            previous = reduce_results(s, previous)
    return previous


class TrailDB(object):

    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.cursor = self.conn.cursor()
        self._init()

    def _init(self):
        self.cursor.execute('''
           create table if not exists events (
              event_date   datetime,
              event_name   varchar(128),
              event_source varchar(128),
              user_agent   varchar(128),
              request_id   varchar(32),
              client_ip    varchar(32),
              user_id      varchar(128),
              error_code   varchar(256),
              error        text
        )''')
# omit due to size
#              response     text,
#              request      text,
#              user         text,
    def insert(self, records):
        self.cursor.executemany(
            "insert into events values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            records)

    def flush(self):
        self.conn.commit()


def reduce_records(x, y):
    if y is None:
        return x
    elif x is None:
        return y
    y.extend(x)
    return y


#STOP = 42
#
#def store_records(output, q):
#    db = TrailDB(output)
#    while True:
#        results = q.get()
#        if results == STOP:
#            return
#        for r in results:
#            for fpath in r:
#                with open(fpath) as fh:
#                    db.insert(load(fh.read()))
#                os.remove(fpath)
#        db.flush()


def process_record_set(object_processor, q):
    def f(*args, **kw):
        r = object_processor(*args, **kw)
        if r:
            q.put(r)
        return r


def process_records(records,
                    uid_filter=None,
                    event_filter=None,
                    service_filter=None,
                    not_service_filter=None,
                    data_dir=None):

    user_records = []
    for r in records:
        if not_service_filter and r['eventSource'] == not_service_filter:
            continue

        utype = r['userIdentity']['type']
        if utype == 'Root':
            uid = 'root'
        elif utype == 'SAMLUser':
            uid = r['userIdentity']['userName']
        else:
            uid = r['userIdentity'].get('arn', '')

        if uid_filter and uid_filter not in uid.lower():
            continue
        elif event_filter and not r['eventName'] == event_filter:
            continue
        elif service_filter and not r['eventSource'] == service_filter:
            continue
        user_records.append((
            r['eventTime'],
            r['eventName'],
            r['eventSource'],
            r.get('userAgent', ''),
            r.get('requestID', ''),
            r['sourceIPAddress'],
            uid,
# TODO make this optional, for now omit for size
#            json.dumps(r['requestParameters']),
#            json.dumps(r['responseElements']),
#            json.dumps(r['userIdentity']),
            r.get('errorCode', None),
            r.get('errorMessage', None)
            ))
    if data_dir:
        if not user_records:
            return
        # Spool to temporary files to get out of mem
        fh = tempfile.NamedTemporaryFile(dir=data_dir, delete=False)
        fh.write(dump(user_records))
        fh.flush()
        fh.close()
        return [fh.name]
    return user_records


def process_bucket(
        bucket_name, prefix,
        output=None, uid_filter=None, event_filter=None,
        service_filter=None, not_service_filter=None, data_dir=None):

    s3 = boto3.Session().client('s3')
    paginator = s3.get_paginator('list_objects')
    # PyPy has some memory leaks.... :-(
    pool = Pool(maxtasksperchild=10)
    t = time.time()
    object_count = object_size = idx = 0

    log.info("Processing:%d cloud-trail %s" % (
        cpu_count(),
        prefix))

    record_processor = partial(
        process_records,
        uid_filter=uid_filter,
        event_filter=event_filter,
        service_filter=service_filter,
        not_service_filter=not_service_filter,
        data_dir=data_dir)

    object_processor = partial(
        process_trail_set,
        map_records=record_processor,
        reduce_results=reduce_records,
        trail_bucket=bucket_name)
    db = TrailDB(output)

    bsize = math.ceil(1000/float(cpu_count()))
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        objects = page.get('Contents', ())
        object_count += len(objects)
        object_size += sum([o['Size'] for o in objects])

        pt = time.time()
        if pool:
            results = pool.map(object_processor, chunks(objects, bsize))
        else:
            results = map(object_processor, chunks(objects, bsize))

        st = time.time()
        log.info("Loaded page time:%0.2fs", st-pt)

        for r in results:
            for fpath in r:
                with open(fpath) as fh:
                    db.insert(load(fh.read()))
                os.remove(fpath)
            db.flush()

        l = t
        t = time.time()

        log.info("Stored page time:%0.2fs", t-st)
        log.info(
            "Processed paged time:%0.2f size:%s count:%s" % (
                t-l, object_size, object_count))
        log.info('Last Page Key: %s', objects[-1]['Key'])


def get_bucket_path(options):
    prefix = "AWSLogs/%(account)s/CloudTrail/%(region)s/" % {
        'account': options.account, 'region': options.region}
    if options.prefix:
        prefix = "%s/%s" % (options.prefix.strip('/'), prefix)
    if options.day:
        date = parse(options.day)
        date_prefix = date.strftime("%Y/%m/%d/")
    if options.month:
        date = parse(options.month)
        date_prefix = date.strftime("%Y/%m/")
    if date_prefix:
        prefix += date_prefix
    return prefix


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--account", required=True)
    parser.add_argument("--user")
    parser.add_argument("--event")
    parser.add_argument("--source")
    parser.add_argument("--not-source")
    parser.add_argument("--day")
    parser.add_argument("--month")
    parser.add_argument("--tmpdir", default="/tmp/traildb")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--output", default="results.db")
    return parser


def main():
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    parser = setup_parser()
    options = parser.parse_args()


    if options.tmpdir and not os.path.exists(options.tmpdir):
        os.makedirs(options.tmpdir)
    prefix = get_bucket_path(options)

    process_bucket(
        options.bucket,
        prefix,
        options.output,
        options.user,
        options.event,
        options.source,
        options.not_source,
        options.tmpdir
        )


if __name__ == '__main__':
    main()
