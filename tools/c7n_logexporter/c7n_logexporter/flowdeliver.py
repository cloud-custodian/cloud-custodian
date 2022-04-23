# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""CWL Group -> Kinesis -> Firehose -> S3 -> Lambda -> S3

Intermediate lambda to convert firehose s3 to log group export format.
"""

import boto3
from datetime import datetime
import gc
import gzip
import json
import logging
import os
import tempfile
import uuid

from urllib.parse import unquote_plus

s3 = boto3.client('s3')
log = logging.getLogger('logregate')

BUCKET = os.environ.get('DESTINATION_BUCKET')
BUCKET_PREFIX = os.environ.get('DESTINATION_PREFIX')
EVENTS_SIZE_BUFFER = int(os.environ.get('EVENTS_SIZE_BUFFER', 1900000))


def handle(event, context):
    gc.collect()
    if 'Records' not in event:
        log.warning("Unknown event source %s", json.dumps(event, indent=2))
        return
    bodies = [
        sns['Sns']['Message'] for sns in event.get('Records')
        if sns.get('EventSource') == "aws:sns"]

    for b in bodies:
        records = json.loads(b).get('Records', ())
        log.info("Received %d Firehose Keys" % len(records))
        for r in records:
            i = r['s3']
            log.warning(
                "Record Processing %s", json.dumps(i, indent=2))
            bucket = i['bucket']['name']
            key = unquote_plus(i['object']['key'])
            size = i['object']['size']
            log.warning(
                "Processing Bucket:%s Key:%s Size:%d", bucket, key, size)
            process_firehose_archive(bucket, key)
            s3.delete_object(Bucket=bucket, Key=key)


def process_firehose_archive(bucket, key):
    """Download firehose archive, aggregate records in memory and write back."""
    data = {}
    with tempfile.NamedTemporaryFile(mode='w+b') as fh:
        s3.download_file(bucket, key, fh.name)
        log.warning("Downloaded Key Size:%s Key:%s",
                    sizeof_fmt(os.path.getsize(fh.name)), key)
        fh.seek(0, 0)
        record_count = 0
        iteration_count = 0
        for r in records_iter(gzip.GzipFile(fh.name, mode='r')):
            record_count += len(r['logEvents'])
            iteration_count += 1
            key = '%s/%s/%s' % (r['owner'], r['logGroup'], r['logStream'])
            data.setdefault(key, []).extend(r['logEvents'])
            if record_count > EVENTS_SIZE_BUFFER:
                log.warning(
                    "Incremental Data Load records:%d enis:%d",
                    record_count,
                    len(data))
                for k in data:
                    process_record_set(k, data[k])
                data.clear()
                gc.collect()
                record_count = 0

        for k in data:
            process_record_set(k, data[k])
        data.clear()
        gc.collect()


def process_record_set(k, records):
    owner, group, stream = k.split('/')
    records_begin = datetime.fromtimestamp(
        records[0]['timestamp'] / 1000)

    records_key = str(uuid.uuid4())
    out_key = "%s/%s/%s/%s/%s/%s/%s.gz" % (
        BUCKET_PREFIX.strip('/'),
        owner,
        group,
        records_begin.strftime('%Y/%m/%d'),
        '00000000-0000-0000-0000-000000000000',
        stream,
        records_key)

    with tempfile.NamedTemporaryFile() as out_fh:
        with gzip.GzipFile(
                records_key, mode='wb',
                fileobj=open(out_fh.name, 'wb')) as records_fh:
            timestamp = None
            record_counter = 0
            buf = []
            for r in records:
                record_counter += 1
                timestamp = datetime.fromtimestamp(
                    r['timestamp'] / 1000).strftime(
                        '%Y-%m-%dT%H:%M:%S.%fZ')
                buf.append('%s %s\n' % (timestamp, r['message']))
                if record_counter % 100 == 0:
                    records_fh.write("".join(buf).encode('utf8'))
                    buf = []
            if buf:
                records_fh.write("".join(buf).encode('utf8'))
            records_fh.close()
            s3.put_object(
                Bucket=BUCKET,
                Key=out_key,
                ACL='bucket-owner-full-control',
                ServerSideEncryption='AES256',
                Body=out_fh.read())


def records_iter(fh, buffer_size=1024 * 1024 * 16):
    """Split up a firehose s3 object into records

    Firehose cloudwatch log delivery of flow logs does not delimit
    record boundaries. We have to use knowledge of content to split
    the records on boundaries. In the context of flow logs we're
    dealing with delimited records.
    """
    buf = None
    while True:
        chunk = fh.read(buffer_size)
        if not chunk:
            if buf:
                yield json.loads(buf)
            return
        if buf:
            chunk = b"%s%s" % (buf, chunk)
            buf = None
        while chunk:
            idx = chunk.find(b'}{')
            if idx == -1:
                buf = chunk
                chunk = None
                continue
            record = chunk[:idx + 1]
            yield json.loads(record)
            chunk = chunk[idx + 1:]


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)
