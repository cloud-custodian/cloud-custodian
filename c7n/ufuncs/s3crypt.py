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

import boto3
import json

from c7n.resources.s3 import EncryptExtantKeys

s3 = config = None


def init():
    global s3, config
    if s3 is not None:
        return

    s3 = boto3.client('s3')
    with open('config.json') as fh:
        config = json.load(fh)


def process_key_event(event, context):
    init()
    processor = EncryptExtantKeys(config)
    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = {'Key': record['s3']['object']['key']}
        version = record['s3']['object'].get('versionId')
        if version is not None:
            result = processor.process_version(s3, key, bucket)
        else:
            result = processor.process_key(s3, key, bucket)
        if not result:
            return
        print("remediated %s:%s" % (bucket, key['Key']))


def get_function(session_factory, role, buckets=None):
    from c7n.mu import (
        LambdaFunction, custodian_archive, BucketNotification)

    config = dict(
        name='custodian-s3-encrypt',
        handler='s3crypt.process_key_event',
        memory_size=256,
        timeout=15,
        role=role,
        runtime="python2.7",
        description='Custodian S3 Key Encrypt')

    if buckets:
        config['events'] = [
            BucketNotification({}, session_factory, b)
            for b in buckets]

    archive = custodian_archive()
    archive.create()

    src = __file__
    if src.endswith('.pyc'):
        src = src[:-1]

    archive.add_file(src, 's3crypt.py')
    archive.add_contents('config.json', json.dumps({}))
    archive.close()
    return LambdaFunction(config, archive)
