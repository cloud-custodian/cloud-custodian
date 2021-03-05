# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Lambda entry point
"""
import boto3
import json
import os

from .sqs_queue_processor import MailerSqsQueueProcessor


def config_setup(config=None):
    task_dir = os.environ.get('LAMBDA_TASK_ROOT')
    os.environ['PYTHONPATH'] = "%s:%s" % (task_dir, os.environ.get('PYTHONPATH', ''))
    if not config:
        with open(os.path.join(task_dir, 'config.json')) as fh:
            config = json.load(fh)
    if 'http_proxy' in config:
        os.environ['http_proxy'] = config['http_proxy']
    if 'https_proxy' in config:
        os.environ['https_proxy'] = config['https_proxy']
    return config


def start_c7n_mailer(logger, config=None, parallel=False):
    try:
        session = boto3.Session()
        if not config:
            config = config_setup()
        logger.info('c7n_mailer starting...')
        mailer_sqs_queue_processor = MailerSqsQueueProcessor(config, session, logger)
        mailer_sqs_queue_processor.run(parallel)
    except Exception as e:
        logger.exception("Error starting mailer MailerSqsQueueProcessor(). \n Error: %s \n" % (e))
