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
Cloud-Maid Lambda Entry Point

Mostly this serves to load up the policy and dispatch
an event.
"""

from cStringIO import StringIO

import logging
import json

from c7n.policy import load
from c7n.utils import format_event


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
        d = {}
        d.update({
            'region': None,
            'cache': '',
            'profile': None,
            'assume_role': None,
            'log_group': None,
            'metrics_enabled': False,
            'output_dir': '/tmp/',
            'cache_period': 0,
            'dryrun': False})
        d.update(kw)
        return cls(d)


def dispatch_event(event, context):
    log.info("Processing event\n %s", format_event(event))

    error = event.get('detail', {}).get('errorCode')
    if error:
        log.debug("Skipping failed operation: %s" % error)
        return

    event['debug'] = True
    policies = load(Config.empty(), 'config.json', format='json')
    for p in policies:
        p.push(event, context)

