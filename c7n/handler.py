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
Cloud-Custodian Lambda Entry Point

Mostly this serves to load up the policy and dispatch
an event.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
import uuid
import json

from c7n.policy import PolicyCollection
from c7n.resources import load_resources
from c7n.utils import format_event, get_account_id_from_sts


logging.root.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)
log = logging.getLogger('custodian.lambda')


# TODO move me / we should load config options directly from policy config
class Config(dict):

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    @classmethod
    def empty(cls, **kw):
        account_id = None
        if 'AWS_LAMBDA_FUNCTION_NAME' in os.environ:
            try:
                import boto3
                session = boto3.Session()
                account_id = get_account_id_from_sts(session)
            except:
                pass

        d = {}
        d.update({
            'region': os.environ.get('AWS_DEFAULT_REGION'),
            'cache': '',
            'profile': None,
            'account_id': account_id,
            'assume_role': None,
            'external_id': None,
            'log_group': None,
            'metrics_enabled': True,
            'output_dir': os.environ.get(
                'C7N_OUTPUT_DIR',
                '/tmp/' + str(uuid.uuid4())),
            'cache_period': 0,
            'dryrun': False})
        d.update(kw)
        if not os.path.exists(d['output_dir']):
            os.mkdir(d['output_dir'])
        return cls(d)


def dispatch_event(event, context):

    error = event.get('detail', {}).get('errorCode')
    if error:
        log.debug("Skipping failed operation: %s" % error)
        return

    event['debug'] = True
    if event['debug']:
        log.info("Processing event\n %s", format_event(event))

    # policies file should always be valid in lambda so do loading naively
    with open('config.json') as f:
        policy_config = json.load(f)

    if not policy_config or not policy_config.get('policies'):
        return False

    # TODO. This enshrines an assumption of a single policy per lambda.
    options_overrides = policy_config[
        'policies'][0].get('mode', {}).get('execution-options', {})
    options = Config.empty(**options_overrides)

    load_resources()
    policies = PolicyCollection.from_data(policy_config, options)
    if policies:
        for p in policies:
            p.push(event, context)
    return True
