# Copyright 2017 Capital One Services, LLC
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

"""VPC Flow log s3 archiver via kinesis cloudwatch subscription.
"""
from __future__ import print_function

from base64 import b64decode
from datetime import datetime
import json
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
    for record in records:
        # https://observable.net/blog/aws-lambda-for-flow-logs-processing/
        compressed_json = b64decode(record['kinesis']['data'])
        uncompressed_json = decompress(compressed_json, 16 + MAX_WBITS)
        input_data = json.loads(uncompressed_json)
        flow_records = input_data['logEvents']
        record_key = str(uuid.uuid4())
        key = "%s/%s/%s/%s.gz" % (
            config['destination']['prefix'].rstrip('/'),
            input_data['owner'], input_data['logStream'], record_key)

        with open('/tmp/%s' % record_key, 'w+') as fh:
            record_file = gzip.GzipFile(record_key, mode='wb', compresslevel=5, fileobj=fh)
            for r in flow_records:
                if timestamp is None:
                    timestamp = datetime.datetime.fromtimestamp(
                        r['timestamp'] / 1000).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                record_file.write("%s %s\n" % (timestamp, r['message']))
            record_file.close()
            fh.seek(0)
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Acl='bucket-owner-full-control',
                ServerSideEncryption='AES256',
                Body=fh)
        os.path.unlink(fh.name)
