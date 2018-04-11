# Copyright 2018 Capital One Services, LLC
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
import base64
import logging

import boto3
import click
import jsonschema
import yaml

from sqs_handler import SQSHandler

CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['queue_url', 'role', 'kms_decrypt_token', 'slack_token'],
    'properties': {
        'queue_url': {'type': 'string'},
        'region': {'type': 'string'},
        'role': {'type': 'string'},
        'contact_tags': {'type': 'array', 'items': {'type': 'string'}},
        'notify_methods': {'type': 'array', 'items': {'type': 'string'}},
        'kms_decrypt_token': {'type': 'string'},
        'slack_token': {'type': 'string'},
        'ldap_uri': {'type': 'string'},
        'ldap_bind_dn': {'type': 'string'},
        'ldap_bind_user': {'type': 'string'},
        'ldap_bind_password': {'type': 'string'},
    }
}


def get_logger(debug):
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    if debug:
        logging.getLogger('botocore').setLevel(logging.DEBUG)
        debug_logger = logging.getLogger('c7n-slacker')
        debug_logger.setLevel(logging.DEBUG)
        return debug_logger
    else:
        return logging.getLogger('c7n-slacker')

@click.group()
def cli():
    """Custodian Slacker"""


@cli.command(name='slacker')
@click.option('-c', '--config', required=True, help="Config file")
def start(config):

    with open(config) as fh:
        config = yaml.load(fh.read(), Loader=yaml.SafeLoader)

    jsonschema.validate(config, CONFIG_SCHEMA)

    if config.get('kms_decrypt_token', True) and config.get('slack_token'):
        kms = boto3.Session(region_name=config.get('region')).client('kms')
        config['slack_token'] = kms.decrypt(
            CiphertextBlob=base64.b64decode(config['slack_token']))['Plaintext']

    message_handler = SQSHandler(config, get_logger(debug=False))

    message_handler.process_sqs(config)

if __name__ == '__main__':
    try:
        start()
    except Exception as e:
        import traceback, pdb, sys
        print traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])