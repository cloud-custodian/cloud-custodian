# coding: utf-8
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
S3 Key Encrypt on Bucket Changes
"""
import json
import boto3
from botocore.exceptions import ClientError
from urllib.parse import unquote_plus
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
        key = {'Key': unquote_plus(record['s3']['object']['key']),
               'Size': record['s3']['object']['size']}
        version = record['s3']['object'].get('versionId')
        if version is not None:
            key['VersionId'] = version
            # lambda event is always latest version, but IsLatest
            # is not in record
            key['IsLatest'] = True
            method = processor.process_version
        else:
            method = processor.process_key
        try:
            result = retry(method, s3, key, bucket)
        except ClientError as e:
            # Ensure we know which key caused an issue
            print("error %s:%s code:%s" % (
                bucket, key['Key'], e.response['Error']))
            raise
        if not result:
            return
        print("remediated %s:%s" % (bucket, key['Key']))


def process_event(event, context):
    for record in event.get('Records', []):
        if 'Sns' in record:
            process_key_event(json.loads(record['Sns']['Message']), context)
        else:
            process_key_event(event, context)


def get_function(session_factory, role, buckets=None, account_id=None, tags=None):
    from c7n.mu import (
        LambdaFunction, custodian_archive, BucketLambdaNotification)

    config = dict(
        name='c7n-s3-encrypt',
        handler='s3crypt.process_event',
        memory_size=256,
        timeout=30,
        role=role,
        tags=tags or {},
        runtime="python2.7",
        description='Custodian S3 Key Encrypt')

    if buckets:
        config['events'] = [
            BucketLambdaNotification(
                {'account_s3': account_id},
                session_factory, b)
            for b in buckets]

    archive = custodian_archive()

    archive.add_py_file(__file__)
    archive.add_contents('config.json', json.dumps({}))
    archive.close()
    return LambdaFunction(config, archive)
