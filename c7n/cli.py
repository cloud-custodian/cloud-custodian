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

import argparse
import logging

from c7n import commands


def _default_options(p):
    p.add_argument("-r", "--region", default="us-east-1",
                   help="AWS Region to target (Default: us-east-1)")
    p.add_argument("--profile", default=None,
                   help="AWS Account Config File Profile to utilize")
    p.add_argument("--assume", default=None, dest="assume_role",
                   help="Role to assume")
    p.add_argument("-c", "--config", required=True,
                   help="Policy Configuration File")
    p.add_argument("-l", "--log-group", default=None,
                   help="Cloudwatch Log Group to send policy logs")
    p.add_argument("-p", "--policies", default=None, dest='policy_filter',
                   help="Only execute named/matched policies")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Verbose Logging")
    p.add_argument("--debug", action="store_true",
                   help="Dev Debug")
    p.add_argument("-s", "--output-dir", required=True,
                   help="Directory or S3 URL For Policy Output")
    p.add_argument("-f", "--cache", default="~/.cache/cloud-custodian.cache")
    p.add_argument("--cache-period", default=60, type=int,
                   help="Cache validity in seconds (Default 60)")


def _dryrun_option(p):
    p.add_argument(
        "-d", "--dryrun", action="store_true",
        help="Don't change infrastructure but verify access.")


def setup_parser():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers()

    report = subs.add_parser("report")
    report.set_defaults(command=commands.report)
    _default_options(report)
    report.add_argument(
        '--days', type=int, default=1,
        help="Number of days of history to consider")
    report.add_argument(
        '--raw', type=argparse.FileType('wb'),
        help="Store raw json of collected records to given file path")

    logs = subs.add_parser('logs')
    logs.set_defaults(command=commands.logs)
    _default_options(logs)

    validate = subs.add_parser('validate')
    validate.set_defaults(command=commands.validate)
    validate.add_argument("-c", "--config", required=True,
                          help="Policy Configuration File")
    validate.add_argument("-v", "--verbose", action="store_true",
                          help="Verbose Logging")
    validate.add_argument("--debug", action="store_true",
                          help="Dev Debug")

    run = subs.add_parser("run")
    run.set_defaults(command=commands.run)
    _default_options(run)
    _dryrun_option(run)
    run.add_argument(
        "-m", "--metrics-enabled",
        default=False, action="store_true",
        help="Emit CloudWatch Metrics (default false)")

    return parser


def main():
    parser = setup_parser()
    options = parser.parse_args()

    level = options.verbose and logging.DEBUG or logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.ERROR)

    try:
        options.command(options)
    except Exception:
        if not options.debug:
            raise
        import traceback
        import pdb
        import sys
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])


if __name__ == '__main__':
    main()
