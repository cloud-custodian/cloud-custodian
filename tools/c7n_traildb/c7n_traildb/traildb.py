# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import argparse
from dateutil.parser import parse
from functools import partial
from gzip import GzipFile
import json
import logging
import math
from multiprocessing import cpu_count, Pool
from c7n.credentials import SessionFactory
import os
import tempfile
import time
import sqlite3

try:
    from cStringIO import StringIO
except ImportError:
    from io import BytesIO as StringIO

from botocore.client import Config


log = logging.getLogger('c7n_traildb')

options = None


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

    session_factory = SessionFactory(
        options.region, options.profile, options.assume_role)

    s3 = session_factory().client(
        's3', config=Config(signature_version='s3v4'))

    previous = None
    for o in object_set:
        body = s3.get_object(Key=o['Key'], Bucket=trail_bucket)['Body']
        fh = GzipFile(fileobj=StringIO(body.read()))
        data = json.load(fh)
        s = map_records(data['Records'])
        if reduce_results:
            previous = reduce_results(s, previous)
    return previous


class TrailDB:

    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.cursor = self.conn.cursor()
        self._init()

    def _init(self):
        command = '''
           create table if not exists events (
              event_date   datetime,
              event_name   varchar(128),
              event_source varchar(128),
              user_agent   varchar(128),
              request_id   varchar(32),
              client_ip    varchar(32),
              user_id      varchar(128),
              error_code   varchar(256),
              error        text'''

        if options.field:
            for field in options.field:
                command += ",\n{}    text".format(field)

        command += ')'
        self.cursor.execute(command)

    def insert(self, records):
        command = "insert into events values (?, ?, ?, ?, ?, ?, ?, ?, ?"

        if options.field:
            command += ', ?' * len(options.field)

        command += ")"
        self.cursor.executemany(command, records)

    def flush(self):
        self.conn.commit()


def reduce_records(x, y):
    if y is None:
        return x
    elif x is None:
        return y
    y.extend(x)
    return y


# STOP = 42
#
# def store_records(output, q):
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

        utype = r['userIdentity'].get('type', None)
        if utype == 'Root':
            uid = 'root'
        elif utype == 'SAMLUser':
            uid = r['userIdentity']['userName']
        elif utype is None and r['userIdentity']['invokedBy'] == 'AWS Internal':
            uid = r['userIdentity']['invokedBy']
        else:
            uid = r['userIdentity'].get('arn', '')

        if uid_filter and uid_filter not in uid.lower():
            continue
        elif event_filter and not r['eventName'] == event_filter:
            continue
        elif service_filter and not r['eventSource'] == service_filter:
            continue

        user_record = (
            r['eventTime'],
            r['eventName'],
            r['eventSource'],
            r.get('userAgent', ''),
            r.get('requestID', ''),
            r.get('sourceIPAddress', ''),
            uid,
            r.get('errorCode', None),
            r.get('errorMessage', None)
        )

        # Optional data can be added to each record.
        # Field names are Case Sensitive.
        if options.field:
            for field in options.field:
                user_record += (json.dumps(r[field]), )

        user_records.append(user_record)

    if data_dir:
        if not user_records:
            return
        # Spool to temporary files to get out of mem
        fh = tempfile.NamedTemporaryFile(dir=data_dir, delete=False, mode='w')
        fh.write(dump(user_records))
        fh.flush()
        fh.close()
        return [fh.name]
    return user_records


def process_bucket(
        bucket_name, prefix,
        output=None, uid_filter=None, event_filter=None,
        service_filter=None, not_service_filter=None, data_dir=None):

    session_factory = SessionFactory(
        options.region, options.profile, options.assume_role)

    s3 = session_factory().client(
        's3', config=Config(signature_version='s3v4'))

    paginator = s3.get_paginator('list_objects')
    # PyPy has some memory leaks.... :-(
    pool = Pool(maxtasksperchild=10)
    t = time.time()
    object_count = object_size = 0

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

    bsize = math.ceil(1000 / float(cpu_count()))
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
        log.info("Loaded page time:%0.2fs", st - pt)

        for r in results:
            for fpath in r:
                with open(fpath) as fh:
                    db.insert(load(fh.read()))
                os.remove(fpath)
            db.flush()

        l = t # NOQA
        t = time.time()

        log.info("Stored page time:%0.2fs", t - st)
        log.info(
            "Processed paged time:%0.2f size:%s count:%s" % (
                t - l, object_size, object_count))
        if objects:
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
    parser.add_argument(
        "--profile", default=os.environ.get('AWS_PROFILE'),
        help="AWS Account Config File Profile to utilize")
    parser.add_argument(
        "--assume", default=None, dest="assume_role",
        help="Role to assume")
    parser.add_argument('--field', action='append',
        help='additonal fields that can be added to each record',
        choices=['userIdentity', 'requestParameters', 'responseElements'])
    return parser


def main():
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    global options
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
