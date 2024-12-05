# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Policy output rename utility
"""

import argparse
import logging
import sys

from boto3.session import Session
from botocore.exceptions import ClientError
from c7n.utils import parse_s3


log = logging.getLogger("custodian.policyrename")


class ArgumentError(Exception):
    pass


def setup_parser():
    desc = ('This utility script will preserve the history of a policy '
            'if it is renamed.  Pass in the old policy name and new '
            'policy name and any old policy output and logs will be '
            'copied to the new policy name. '
            'This utility can also be used to re-encrypt your logs '
            'by providing your SSE-KMS key. If the old and new targets '
            'are the same, it will re-encrypt in-place')

    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-v', '--verbose', default=False, action="store_true")
    parser.add_argument('--sse-kms-key-id',
                        help="Key id for SSE-KMS encrypted objects")
    parser.add_argument('-s', '--output-dir', required=True,
                        help="Directory or S3 URL For Policy Output")
    parser.add_argument("old", help="Old policy name")
    parser.add_argument("new", help="New policy name")

    return parser


def s3_rename(output_dir, old, new, sse_kms_key_id):
    # move the old data into the new area
    session = Session()
    client = session.client('s3')
    s3 = session.resource('s3')
    _, bucket, _ = parse_s3(output_dir)

    # Ensure bucket exists
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        raise ArgumentError('S3 bucket {} does not exist.'.format(bucket))

    log.info(
        'Retrieving list of S3 objects to rename in bucket "{}"'.format(
            bucket
        )
    )
    paginator = client.get_paginator('list_objects_v2')
    rename_iterator = paginator.paginate(Bucket=bucket, Prefix=old + '/')
    obj_count = 0

    for page in rename_iterator:
        # loop through the pages of results renaming

        if page.get('Contents') is None:
            raise ArgumentError('Key {} does not exist in bucket {}'.format(
                old, bucket))

        # Loop through the old objects copying and deleting
        for obj in page.get('Contents'):
            old_key = obj.get('Key')
            old_meta = client.head_object(Bucket=bucket, Key=old_key)
            old_sse_type = old_meta.get('ServerSideEncryption')
            old_sse_key = old_meta.get('SSEKMSKeyId')
            new_key = new + old_key[len(old):]

            # check that we haven't already run and have existing data
            # in the new key
            new_obj = s3.Object(bucket, new_key)
            if new_key == old_key:
                log.debug(('Old and new keys match and new SSEKMSKeyId '
                         'Specified, re-encrypting {}').format(new_obj.key))
            else:
                try:
                    new_obj.load()
                    if new_key != old_key:
                        log.info('Skipping existing output in new '
                                 'location: {}'.format(new_obj.key))
                        continue
                except ClientError as e:
                    response_code = e.response.get('Error').get('Code')
                    if response_code == '404':
                        # the obj doesn't exist so we will copy
                        # the existing obj to the new spot
                        pass
                    else:
                        raise

            copy_from_args = dict(
                CopySource={
                    'Bucket': bucket,
                    'Key': old_key,
                    'MetadataDirective': 'COPY'
                })

            if sse_kms_key_id:
                # Re-encrypt with a new key
                copy_from_args['ServerSideEncryption'] = 'aws:kms'
                copy_from_args['SSEKMSKeyId'] = sse_kms_key_id
            if not sse_kms_key_id and old_sse_type == 'aws:kms':
                # Re-encrypt with the existing key
                copy_from_args['ServerSideEncryption'] = 'aws:kms'
                copy_from_args['SSEKMSKeyId'] = old_sse_key
            if not sse_kms_key_id and old_sse_type == 'AES256':
                # Re-encrypt with the existing AES256
                copy_from_args['ServerSideEncryption'] = 'AES256'

            new_obj.copy_from(**copy_from_args)
            log.debug('Renamed "{}" to "{}"'.format(old_key, new_key))
            # Either way, we delete the old object unless we are inplace
            # re-encrypting
            if new_key != old_key:
                s3.Object(bucket, old_key).delete()
                log.debug('Deleted "{}"'.format(old_key))
            obj_count += 1

        log.info(('Finished renaming/re-encrypting '
                  '{} objects').format(obj_count))


def main():
    parser = setup_parser()
    options = parser.parse_args()

    level = options.verbose and logging.DEBUG or logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.ERROR)

    if options.output_dir.startswith('s3://'):
        try:
            s3_rename(options.output_dir,
                      options.old,
                      options.new,
                      options.sse_kms_key_id)
        except ArgumentError as e:
            print(e.message)
            sys.exit(2)
    else:
        print("This tool only works for policy output stored on S3. ",
              "To move locally stored output rename",
              "`{}/{}`".format(options.output_dir, options.old),
              "to `{}/{}`.".format(options.output_dir, options.new))


if __name__ == '__main__':
    main()
