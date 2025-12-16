# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry

from c7n_snowflake.resources.resource_map import ResourceMap
from c7n_snowflake.session import SessionFactory


@clouds.register("snowflake")
class Snowflake(Provider):
    display_name = "Snowflake"
    resource_prefix = "snowflake"
    resources = PluginRegistry("%s.resources" % resource_prefix)
    resource_map = ResourceMap

    def initialize(self, options):
        pass

    def initialize_policies(self, policy_collection, options):
        # not handling any options right now
        return policy_collection

    def get_session_factory(self, options):
        return SessionFactory()


resources = Snowflake.resources
