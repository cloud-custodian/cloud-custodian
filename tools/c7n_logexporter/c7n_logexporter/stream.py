# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""VPC Flow log s3 archiver via kinesis cloudwatch subscription.
"""
from base64 import b64decode
from collections import Counter
from datetime import datetime
import json
import gc
import gzip
import logging
import os
import uuid
from zlib import decompress, MAX_WBITS

import boto3


def load_config():
    with open('config.json') as fh:
        return json.load(fh)


config = load_config()
s3 = boto3.client('s3')
log = logging.getLogger('c7n_logexporter')


def handler(event, context):
    records = event.get('Records', [])
    bucket = config['destination']['bucket']
    timestamp = None

    counter_bytes = 0
    counter_raw_bytes = 0
    counter_records = 0
    counter_enis = Counter()

    eni_records = {}
    eni_accounts = {}

    for record in records:
        counter_records += 1
        counter_bytes += len(record['kinesis']['data'])

        # https://observable.net/blog/aws-lambda-for-flow-logs-processing/
        compressed_json = b64decode(record['kinesis']['data'])
        uncompressed_json = decompress(compressed_json, 16 + MAX_WBITS)
        counter_raw_bytes += len(uncompressed_json)

        input_data = json.loads(uncompressed_json)
        flow_records = input_data['logEvents']

        eni = input_data['logStream']
        # batch in memory... to get some larger archives
        if eni not in eni_records:
            eni_records[eni] = []
            eni_accounts[eni] = input_data['owner']
        counter_enis[eni] += 1
        eni_records[eni].extend(flow_records)

    for eni, flow_records in eni_records.items():
        records_begin = datetime.fromtimestamp(
            flow_records[0]['timestamp'] / 1000)

        owner = eni_accounts[eni]
        record_key = str(uuid.uuid4())

        key = "%s/%s/%s/%s/%s/%s.gz" % (
            config['destination']['prefix'].rstrip('/'),
            owner,
            records_begin.strftime('%Y/%m/%d'),
            '00000000-0000-0000-0000-000000000000',
            eni,
            record_key)

        with open('/tmp/%s' % record_key, 'w+') as fh:
            record_file = gzip.GzipFile(record_key, mode='wb', compresslevel=5, fileobj=fh)
            for r in flow_records:
                if timestamp is None:
                    timestamp = datetime.fromtimestamp(
                        r['timestamp'] / 1000).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                record_file.write("%s %s\n" % (timestamp, r['message']))
            record_file.close()
            fh.seek(0)
            s3.put_object(
                Bucket=bucket,
                Key=key,
                ACL='bucket-owner-full-control',
                ServerSideEncryption='AES256',
                Body=fh)
        os.unlink(fh.name)

    eni_records_count = {k: len(v) for k, v in eni_records.items()}
    eni_records.clear()
    gc.collect()

    print(
        json.dumps(dict(
            records=counter_records,
            bytes=counter_bytes,
            log_bytes=counter_raw_bytes,
            eni_log_records=dict(counter_enis),
            eni_flow_records=eni_records_count)))
