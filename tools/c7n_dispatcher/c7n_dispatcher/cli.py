# Copyright 2017 Capital One Services, LLC
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
""" SQS Dispatcher for sending custodian notifications to Elasticsearch
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import boto3
import click
import functools
import jsonschema
import logging
import yaml

from c7n_dispatcher import handler

CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['queue_url', 'endpoint'],
    'properties': {
        'queue_url': {'type': 'string'},
        'http_proxy': {'type': 'string'},
        'https_proxy': {'type': 'string'},

        # Standard Lambda Function Config
        'region': {'type': 'string'},
        'role': {'type': 'string'},
        'memory': {'type': 'integer'},
        'timeout': {'type': 'integer'},
        'subnets': {'type': 'array', 'items': {'type': 'string'}},
        'security_groups': {'type': 'array', 'items': {'type': 'string'}},
        'dead_letter_config': {'type': 'object'},


        'messenger': {
            # Add support for other DB types?
            'oneOf': [
                {
                    'type': 'object',
                    'required': ['host', 'port', 'index'],
                    'properties': {
                        'type': {'enum': ['elasticsearch']},
                        'host': {'type': 'string'},
                        'port': {'type': 'number'},
                        'user': {'type': 'string'},
                        'password': {'type': 'string'},
                        'index': {'type': 'string'}
                    }
                }
            ]
        }
    }
}


def get_logger(debug=False):
    logging.basicConfig(level=(debug and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)
    if debug:
        logging.getLogger('botocore').setLevel(logging.DEBUG)
        return logging.getLogger('custodian-dispatcher').setLevel(logging.DEBUG)
    return logging.getLogger('custodian-dispatcher')


def session_factory(config):
    return boto3.Session(
        region_name=config['region']
    )


@click.group()
def cli():
    """ Custodian SQS Dispatcher """


@cli.command()
@click.option('-c', '--config', required=True, help="Config file")
@click.option('--debug/--no-debug', default=False)
def deploy(config, debug=False):
    # validate the config file
    with open(config) as fh:
        config = yaml.safe_load(fh.read())
    jsonschema.validate(config, CONFIG_SCHEMA)
    handler.provision(config, functools.partial(session_factory, config))


# TODO: add run command for local processing


def main():
    try:
        cli()
    except Exception as e:
        import traceback, pdb, sys
        print(e, traceback.print_exc())
        pdb.post_mortem(sys.exc_info()[-1])


if __name__ == '__main__':
    main()
