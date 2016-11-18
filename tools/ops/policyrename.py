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
    parser = argparse.ArgumentParser()
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


def local_rename(output_dir, old, new):
    """ Rename a local filesystem directory to a new name.
    
    Merge over existing files if applicable.
    """
    old_dir = os.path.join(output_dir, old)
    new_dir = os.path.join(output_dir, new)

    # If the old_dir doesn't exist, there is nothing to do.
    if not os.path.exists(old_dir):
        raise ArgumentError(
            "Error: There is no existing output for a policy with name {}.".format(old_dir))

    # If the new_dir doesn't exist yet, just rename the old one and we're done.
    if not os.path.exists(new_dir):
        os.rename(old_dir, new_dir)
        print("Successfully renamed policy {} to {}.".format(old_dir, new_dir))
        return
        
    # If there are files in both places we want to be more careful.  There is a
    # log file that we want to concatenate together.  For all other files,
    # we want to keep whatever is in the newer directory.
    old_file = os.path.join(old_dir, 'custodian-run.log')
    new_file = os.path.join(new_dir, 'custodian-run.log')
    old_file_exists = os.path.exists(old_file)
    new_file_exists = os.path.exists(new_file)
    
    if old_file_exists and new_file_exists:
        tmp_file = os.path.join(old_dir, 'tmp-rename-{}.log'.format(os.getpid()))
        with open(tmp_file, 'w') as fout:
            for line in fileinput.input([old_file, new_file]):
                fout.write(line)
        os.rename(tmp_file, new_file)
    elif old_file_exists:
        shutil.copy(old_file, new_file)

    # We could do a shutil.rmtree(old_dir) here, but there is lots of potential
    # for Bad Things to happen if the user supplies bad inputs
    # (e.g. if they give output-dir='/' and old='' we would do shutil.rmtree('/'))
    #
    # So we'll just leave the old directory alone. Note that it only gets left
    # behind if old_dir *and* new_dir exist.  In the case where new_dir did not
    # yet exist, old_dir would be renamed and nothing would be left behind.
    print("Output files existed for both policies.  The log files were merged",
          "and all files from the new directory were left in place.\n")
    print("To delete the old policy output directory run:")
    print("  rm -fr {}".format(old_dir))


def main():
    parser = setup_parser()
    options = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.ERROR)

    try:
        if options.output_dir.startswith('s3://'):
            s3_rename(options.output_dir, options.old, options.new)
        else:
            local_rename(options.output_dir, options.old, options.new)
    except ArgumentError as e:
        print(e.message)
        sys.exit(2)


if __name__ == '__main__':
    main()
