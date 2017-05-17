"""
Allow local testing of mailer and templates by replaying an SQS message.

MAILER_FILE input is a file containing the exact base64-encoded, gzipped
data that's enqueued to SQS via :py:meth:`c7n.actions.Notify.send_sqs`.

Alternatively, with -p|--plain specified, the file will be assumed to be
JSON data that can be loaded directly.
"""

import argparse
import boto3
import os
import logging
import zlib
import base64
import json

import jsonschema
import yaml

from c7n import utils
from c7n_mailer.utils import setup_defaults
from .sqs_message_processor import SqsMessageProcessor

logger = logging.getLogger(__name__)


CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['queue_url', 'role', 'from_address'],
    'properties': {
        'queue_url': {'type': 'string'},
        'from_address': {'type': 'string'},
        'contact_tags': {'type': 'array', 'items': {'type': 'string'}},

        # Standard Lambda Function Config
        'region': {'type': 'string'},
        'role': {'type': 'string'},
        'memory': {'type': 'integer'},
        'timeout': {'type': 'integer'},
        'subnets': {'type': 'array', 'items': {'type': 'string'}},
        'security_groups': {'type': 'array', 'items': {'type': 'string'}},

        # Mailer Infrastructure Config
        'cache': {'type': 'string'},
        'smtp_server': {'type': 'string'},
        'smtp_port': {'type': 'integer'},
        'smtp_ssl': {'type': 'boolean'},
        'smtp_username': {'type': 'string'},
        'smtp_password': {'type': 'string'},
        'ldap_uri': {'type': 'string'},
        'ldap_bind_dn': {'type': 'string'},
        'ldap_bind_user': {'type': 'string'},
        'ldap_bind_password': {'type': 'string'},
        'cross_accounts': {'type': 'object'},
        'ses_region': {'type': 'string'},

        # SDK Config
        'profile': {'type': 'string'},
        'http_proxy': {'type': 'string'},
        'https_proxy': {'type': 'string'},
    }
}


class MailerTester(object):

    def __init__(self, msg_file, config, msg_plain=False):
        if not os.path.exists(msg_file):
            raise RuntimeError("File does not exist: %s" % msg_file)
        logger.debug('Reading message from: %s', msg_file)
        with open(msg_file, 'r') as fh:
            raw = fh.read()
        logger.debug('Read %d byte message', len(raw))
        if msg_plain:
            raw = raw.strip()
        else:
            logger.debug('base64-decoding and zlib decompressing message')
            raw = zlib.decompress(base64.b64decode(raw))
        self.data = json.loads(raw)
        logger.debug('Loaded message JSON')
        self.config = config
        self.session = boto3.Session()

    def run(self, dry_run=False, print_only=False):
        msg = {
            'Body': base64.b64encode(zlib.compress(utils.dumps(self.data))),
            'MessageId': 'replayed-message'
        }
        self.show_to(msg)
        if print_only:
            self.do_print()
            return
        if dry_run:
            self.do_dry_run(msg)
            return
        smp = SqsMessageProcessor(self.config, self.session, None, logger)
        smp.process_sqs_messsage(msg)

    def do_dry_run(self, msg):
        def sre(RawMessage):
            logger.info("SEND RAW MESSAGE:")
            print(RawMessage['Data'])

        if self.config.get('smtp_server'):
            del self.config['smtp_server']
        smp = SqsMessageProcessor(self.config, self.session, None, logger)
        smp.aws_ses.send_raw_email = sre
        smp.process_sqs_messsage(msg)

    def do_print(self):
        def sce(_, email_to, subject, body):
            logger.info('Send mail with subject "%s":', subject)
            print(body)
            raise SystemExit(0)

        smp = SqsMessageProcessor(self.config, self.session, None, logger)
        smp.send_c7n_email = sce
        smp.send_message_to_targets(
            ['foo@example.com'], self.data, self.data['resources']
        )

    def show_to(self, msg):
        def smtt(targets, _, resources):
            logger.info('Would send email for %s resources to: %s',
                        len(resources), targets)
        smp = SqsMessageProcessor(self.config, self.session, None, logger)
        smp.send_message_to_targets = smtt
        smp.process_sqs_messsage(msg)


def setup_parser():
    parser = argparse.ArgumentParser('Test c7n-mailer templates and mail')
    parser.add_argument('-c', '--config', required=True)
    parser.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                        default=False,
                        help='Log messages that would be sent, but do not send')
    parser.add_argument('-t', '--template-print', dest='print_only',
                        action='store_true', default=False,
                        help='Just print rendered templates')
    parser.add_argument('-p', '--plain', dest='plain', action='store_true',
                        default=False,
                        help='Expect MESSAGE_FILE to be a plain string, '
                             'rather than the base64-encoded, gzipped SQS '
                             'message format')
    parser.add_argument('MESSAGE_FILE', type=str,
                        help='Path to SQS message dump/content file')
    return parser


def session_factory(config):
    return boto3.Session(
        region_name=config['region'],
        profile_name=config.get('profile'))


def main():
    parser = setup_parser()
    options = parser.parse_args()

    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format)
    logging.getLogger('botocore').setLevel(logging.WARNING)

    with open(options.config) as fh:
        config = yaml.load(fh.read(), Loader=yaml.SafeLoader)

    jsonschema.validate(config, CONFIG_SCHEMA)
    setup_defaults(config)

    tester = MailerTester(options.MESSAGE_FILE, config, msg_plain=options.plain)
    tester.run(options.dry_run, options.print_only)


if __name__ == '__main__':
    main()
