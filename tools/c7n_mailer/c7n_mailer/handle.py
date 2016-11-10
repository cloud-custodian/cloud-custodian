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

import base64
import boto3
import getpass
import json
import logging
import os


logging.root.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)

log = logging.getLogger('custodian.mailer')


def bootstrap():
    log.debug("Initializing")
    task_dir = os.environ.get('LAMBDA_TASK_ROOT')
    os.environ['PYTHONPATH'] = "%s:%s" % (task_dir, os.environ.get('PYTHONPATH', ''))
    with open(os.path.join(task_dir, 'config.json')) as fh:
        config = json.load(fh)
    if 'ldap_bind_password' in config:
        kms = session.client('kms')
        config['ldap_bind_password'] = kms.decrypt(
            CiphertextBlob=base64.b64decode(config['ldap_bind_password']))[
                'Plaintext']
    if 'http_proxy' in config:
        os.environ['http_proxy'] = config['http_proxy']
    if 'https_proxy' in config:
        os.environ['https_proxy'] = config['https_proxy']
    return config

session = boto3.Session()
config = bootstrap()


def run(event, context):
    try:
        from markupsafe import Markup
        from jinja2 import utils
        from .worker import Worker
        from .processor import Processor
    except Exception as e:
        log.exception("import failed %s", e)

    try:
        log.info("Worker Run")
        w = Worker(config, context, session)
        w.run()
    except:
        log.exception("Error processing worker \n DebugEnv: %s \n User: %s \n" % (
            os.environ['PYTHONPATH'],
            getpass.getuser()))
