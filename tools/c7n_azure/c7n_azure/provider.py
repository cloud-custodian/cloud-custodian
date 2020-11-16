# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from functools import partial

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry
from c7n.utils import local_session
from .session import Session

from c7n_azure.resources.resource_map import ResourceMap


@clouds.register('azure')
class Azure(Provider):

    display_name = 'Azure'
    resource_prefix = 'azure'
    resources = PluginRegistry('%s.resources' % resource_prefix)
    resource_map = ResourceMap

    def initialize(self, options):
        if options['account_id'] is None:
            session = local_session(self.get_session_factory(options))
            options['account_id'] = session.get_subscription_id()
        options['cache'] = 'memory'
        return options

    def initialize_policies(self, policy_collection, options):
        return policy_collection

    def get_session_factory(self, options):
        return partial(Session,
                       subscription_id=options.account_id,
                       authorization_file=options.authorization_file)


resources = Azure.resources
