# Copyright 2016-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import json


def setup_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True)
    parser.add_argument('-e', '--env', choices=('prod', 'dev'))
    parser.add_argument('-r', '--region', action='append', dest='regions')
    parser.add_argument('-a', '--account', action='append', dest='accounts')
    return parser


def get_accounts(options):
    with open(options.config) as fh:
        account_data = json.load(fh)

    if options.accounts:
        accounts = [v for k, v in account_data.items()
                    if k in options.accounts]
    elif options.env:
        accounts = [v for k, v in account_data.items()
                    if k.endswith(options.env)]
    else:
        accounts = account_data.values()
    return accounts
