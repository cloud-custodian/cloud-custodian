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

from c7n.registry import PluginRegistry
from c7n.provider import Provider, clouds

from .client import Session
from functools import partial

import logging

log = logging.getLogger('custodian.k8s')


@clouds.register('k8s')
class Kubernetes(Provider):

    resource_prefix = 'k8s'
    resources = PluginRegistry('%s.resources' % resource_prefix)

    def initialize(self, options):
        return options

    def initialize_policies(self, policy_collection, options):
        return policy_collection

    def get_session_factory(self, options):
        """Get a credential/session factory for api usage."""
        return partial(Session, config_file=options.get('config_file'))


resources = Kubernetes.resources
