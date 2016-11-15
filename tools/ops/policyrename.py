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


def rename_s3_output_dir(output_dir, old, new):


def rename_local_output_dir(output_dir, old, new):


def main():
    parser = setup_parser()
    options = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('botocore').setLevel(logging.ERROR)

    output_dir = getattr(options, 'output_dir', '')
    if output_dir.startswith('s3://'):
        rename_s3_ouput_dir(output_dir, old, new)
    else:
        rename_local_ouput_dir(output_dir, old, new)


if __name__ == '__main__':
    main()
