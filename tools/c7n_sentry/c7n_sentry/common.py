# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
