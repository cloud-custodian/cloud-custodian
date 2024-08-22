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

import copy
import logging
import operator
import os
import sys

from c7n_aliyun.resources.resource_map import ResourceMap

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry
from .client import Session

log = logging.getLogger('custodian.c7n_aliyun')

@clouds.register('aliyun')
class AliyunCloud(Provider):

    display_name = 'Aliyun'
    resource_prefix = 'aliyun'
    resources = PluginRegistry('%s.resources' % resource_prefix)
    resource_map = ResourceMap

    def initialize(self, options):
        _default_region(options)
        return options

    def initialize_policies(self, policy_collection, options):
        return policy_collection


    def initialize_policies(self, policy_collection, options):
        from c7n.policy import Policy, PolicyCollection
        policies = []
        region = options['regions'][0]
        for p in policy_collection:
            options_copy = copy.copy(options)
            options_copy.region = str(region)
            policies.append(Policy(p.data, options_copy, session_factory=policy_collection.session_factory()))
        return PolicyCollection(
            sorted(policies, key=operator.attrgetter('options.region')), options)

    def get_session_factory(self, options):
        """Get a credential/session factory for api usage."""
        return Session


def _default_region(options):
    marker = object()
    value = getattr(options, 'regions', marker)
    if value is marker:
        return

    if len(value) > 0:
        return

    try:
        options.regions = [os.getenv('ALIYUN_DEFAULT_REGION')]
    except Exception:
        log.warning('Could not determine default region')
        options.regions = [None]

    if options.regions[0] is None:
        log.error('No default region set. Specify a default via ALIYUN_DEFAULT_REGION')
        sys.exit(1)

    log.debug("using default region:%s from ALIYUN_DEFAULT_REGION" % options.regions[0])

resources = AliyunCloud.resources
