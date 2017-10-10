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

from __future__ import absolute_import, division, print_function, unicode_literals

import boto3
import json
import logging
import os

from .dispatcher import Dispatcher


def get_config():
    with open('config.json') as fh:
        config = json.load(fh)
    if 'http_proxy' in config:
        os.environ['http_proxy'] = config['http_proxy']
    if 'https_proxy' in config:
        os.environ['https_proxy'] = config['https_proxy']
    return config


def get_logger():
    logger = logging.getLogger('custodian.dispatcher')
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    return logger


def invoke(event, context):
    config = get_config()
    logger = get_logger()
    try:
        session = boto3.Session()
        logger.info('c7n_dispatcher starting...')
        dispatcher = Dispatcher(config, logger, session)
        dispatcher.run()
    except Exception as e:
        logger.exception(
            "Error processing dispatch queue.\nError: {}\n".format(e))


def provision(config, session_factory):
    from c7n.mu import (
        CloudWatchEventSource,
        LambdaFunction,
        LambdaManager,
        PythonPackageArchive
    )

    func_config = dict(
        name='cloud-custodian-dispatcher',
        description='Cloud Custodian SQS Dispatcher',
        handler='handler.invoke',
        runtime='python2.7',
        memory_size=config['memory'],
        timeout=config['timeout'],
        role=config['role'],
        subnets=config['subnets'],
        security_groups=config['security_groups'],
        dead_letter_config=config.get('dead_letter_config', {}),
        events=[
            CloudWatchEventSource(
                {'type': 'periodic',
                 'schedule': 'rate(5 minutes)'},
                session_factory,
                prefix="")
        ]
    )

    archive = PythonPackageArchive('c7n')
    archive.add_py_file(__file__)
    archive.add_file('dispatcher.py')
    archive.add_contents('config.json', json.dumps(config))
    archive.close()

    function = LambdaFunction(func_config, archive)
    manager = LambdaManager(session_factory)
    manager.publish(function)
