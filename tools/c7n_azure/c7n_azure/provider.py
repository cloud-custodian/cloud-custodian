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

from functools import partial

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry
from c7n.utils import local_session
from .session import Session


@clouds.register('azure')
class Azure(Provider):

    resource_prefix = 'azure'
    resources = PluginRegistry('%s.resources' % resource_prefix)

    def initialize(self, options):
        session = local_session(self.get_session_factory(options))
        options['account_id'] = session.get_subscription_id()
        return options

    def initialize_policies(self, policy_collection, options):
        return policy_collection

    def get_session_factory(self, options):
        return partial(Session,
                       subscription_id=options.account_id,
                       authorization_file=options.authorization_file)


resources = Azure.resources
