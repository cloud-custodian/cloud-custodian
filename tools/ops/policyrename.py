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

import argparse
import logging

from boto3.session import Session
from botocore.exceptions import ClientError
from c7n.utils import parse_s3

log = logging.getLogger("custodian.policyrename")


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", "-s", required=True,
                        help="Directory or S3 URL For Policy Output")
    parser.add_argument("old",
                        help="Old policy name")
    parser.add_argument("new",
                        help="New policy name")

    return parser


def s3_rename(output_dir, old, new):
    # move the old data into the new area
    session = Session()
    client = session.client('s3')
    s3 = session.resource('s3')
    s3_path, bucket, key_prefix = parse_s3(output_dir)
    try:
        log.info(
            'Retrieving list of S3 objects to rename in bucket "{}"'.format(
                bucket
            )
        )
        to_rename = client.list_objects(Bucket=bucket, Prefix=old + '/')
    except ClientError as e:
        log.error(e.message)

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
        s3_rename(options.output_dir, options.old, options.new)
    else:
        pass
        #local_rename()


if __name__ == '__main__':
    main()
