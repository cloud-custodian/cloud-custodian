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
"""
Lambda entry point
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import base64
import boto3
import json
import os

from .sqs_queue_processor import MailerSqsQueueProcessor


def config_setup(session):
    task_dir = os.environ.get('LAMBDA_TASK_ROOT')
    os.environ['PYTHONPATH'] = "%s:%s" % (task_dir, os.environ.get('PYTHONPATH', ''))
    with open(os.path.join(task_dir, 'config.json')) as fh:
        config = json.load(fh)
    if config['ldap_bind_password']:
        kms = session.client('kms')
        config['ldap_bind_password'] = kms.decrypt(
            CiphertextBlob=base64.b64decode(config['ldap_bind_password']))[
                'Plaintext']
    if 'http_proxy' in config:
        os.environ['http_proxy'] = config['http_proxy']
    if 'https_proxy' in config:
        os.environ['https_proxy'] = config['https_proxy']
    return config


def start_c7n_mailer(event, context, logger):
    try:
        session = boto3.Session()
        config = config_setup(session)
        mailer_sqs_queue_processor = MailerSqsQueueProcessor(config, session, logger)
        mailer_sqs_queue_processor.run()
    except Exception as e:
        logger.exception("Error starting mailer MailerSqsQueueProcessor(). \n Error: %s \n" % (e))
