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
"""Policy output rename utility
"""

from __future__ import print_function

import argparse
import fileinput
import logging
import os
import shutil
import sys

from boto3.session import Session
from botocore.exceptions import ClientError
from c7n.utils import parse_s3


log = logging.getLogger("custodian.policyrename")


class ArgumentError(Exception): pass


def setup_parser():
    desc = ('This utility script will preserve the history of a policy '
            'if it is renamed.  Pass in the old policy name and new '
            'policy name and any old policy output and logs will be '
            'copied to the new policy name.')

    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-s', '--output-dir', required=True,
                        help="Directory or S3 URL For Policy Output")
    parser.add_argument("old", help="Old policy name")
    parser.add_argument("new", help="New policy name")

    return parser


def s3_rename(output_dir, old, new):
    # move the old data into the new area
    session = Session()
    client = session.client('s3')
    s3 = session.resource('s3')
    s3_path, bucket, key_prefix = parse_s3(output_dir)
    
    # Ensure bucket exists
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        raise ArgumentError('S3 bucket {} does not exist.'.format(bucket))

    try:
        log.info(
            'Retrieving list of S3 objects to rename in bucket "{}"'.format(
                bucket
            )
        )
        to_rename = client.list_objects(Bucket=bucket, Prefix=old + '/')
    except ClientError as e:
        log.error(e.message)

    if to_rename is None or to_rename.get('Contents') is None:
        raise ArgumentError('Key {} does not exist in bucket {}'.format(
                old, bucket))

    # Loop through the old objects copying and deleting
    for obj in to_rename.get('Contents'):
        old_key = obj.get('Key')
        new_key = new + old_key[len(old):]

        # check that we haven't already run and have existing data
        # in the new key
        new_obj = s3.Object(bucket, new_key)
        try:
            new_obj.load()
            log.info('Skipping existing output in new location: {}'.format(
                new_obj.key))
        except ClientError as e:
            response_code = e.response.get('Error').get('Code')
            if response_code == '404':
                new_obj.copy_from(
                    CopySource={'Bucket': bucket, 'Key': old_key}
                )
                log.debug('Renamed "{}" to "{}"'.format(old_key, new_key))
        # Either way, we delete the old object
        s3.Object(bucket, old_key).delete()
        log.debug('Deleted "{}"'.format(old_key))


def main():
    parser = setup_parser()
    options = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.ERROR)

    if options.output_dir.startswith('s3://'):
        try:
            s3_rename(options.output_dir, options.old, options.new)
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
