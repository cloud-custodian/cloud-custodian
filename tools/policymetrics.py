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
from dateutil.parser import parse
from datetime import datetime, timedelta
import logging
import os

from c7n.credentials import SessionFactory
from c7n.policy import load
from c7n.resources import load_resources
from c7n.utils import dumps


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True)
    parser.add_argument('--assume', dest="assume_role")
    parser.add_argument('--profile')
    parser.add_argument(
        '--region', default=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
    parser.add_argument('--start', type=parse)
    parser.add_argument('--end', type=parse)
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--period', type=int, default=60*24*24)
    return parser


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)

    parser = setup_parser()
    options = parser.parse_args()
    options.log_group = None
    options.cache = None

    factory = SessionFactory(
        options.region, options.profile, options.assume_role)

    session = factory()
    client = session.client('cloudwatch')

    load_resources()
    policies = load(options, options.config)

    if options.start and options.end:
        start = options.start
        end = options.end
    elif options.days:
        end = datetime.utcnow()
        start = end - timedelta(options.days)
    data = {}
    for p in policies:
        logging.info('Getting %s metrics', p)
        data[p.name] = p.get_metrics(start, end, options.period)
    print dumps(data, indent=2)


if __name__ == '__main__':
    main()
