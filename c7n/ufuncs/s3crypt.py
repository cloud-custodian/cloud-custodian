# coding: utf-8
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
"""
S3 Key Encrypt on Bucket Changes
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import json

import boto3
from botocore.exceptions import ClientError

from c7n.resources.s3 import EncryptExtantKeys
from c7n.utils import get_retry

s3 = config = None
retry = get_retry(['404', '503'], max_attempts=4, min_delay=2)


def init():
    global s3, config
    if s3 is not None:
        return

    s3 = boto3.client('s3')
    with open('config.json') as fh:
        config = json.load(fh)
        # multipart copy can on multigb file can take a long time
        config['large'] = False


def process_key_event(event, context):
    processor = EncryptExtantKeys(config)
    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = {'Key': record['s3']['object']['key'],
               'Size': record['s3']['object']['size']}
        version = record['s3']['object'].get('versionId')
        try:
            if version is not None:
                key['VersionId'] = version
                # lambda event is always latest version, but IsLatest
                # is not in record
                key['IsLatest'] = True
                result = retry(processor.process_version, s3, key, bucket)
            else:
                result = retry(processor.process_key, s3, key, bucket)
        except ClientError as e:
            # Ensure we know which key caused an issue
            print("error %s:%s code:%s" % (
                bucket, key['Key'], e.response['Error']))
            raise
        if not result:
            return
        print("remediated %s:%s" % (bucket, key['Key']))


def process_sns_event(event, context):
    for record in event.get('Records', []):
        process_key_event(json.loads(record['Sns']['Message']), context)


def get_function(session_factory, role, via_sns, buckets=None, account_id=None):
    from c7n.mu import (
        LambdaFunction, custodian_archive, BucketLambdaNotification)

    config = dict(
        name='c7n-s3-encrypt',
        handler='s3crypt.process_%s' % (via_sns and 'sns_event' or 'key_event'),
        memory_size=256,
        timeout=30,
        role=role,
        runtime="python2.7",
        description='Custodian S3 Key Encrypt')

    if buckets:
        config['events'] = [
            BucketLambdaNotification({'account_s3': account_id},
                session_factory, b)
            for b in buckets]

    archive = custodian_archive()

    archive.add_py_file(__file__)
    archive.add_contents('config.json', json.dumps({}))
    archive.close()
    return LambdaFunction(config, archive)
