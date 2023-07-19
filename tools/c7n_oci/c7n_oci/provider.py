# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n_oci.resources.resource_map import ResourceMap

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry

from .session import SessionFactory

log = logging.getLogger("custodian.provider")


@clouds.register("oci")
class OCI(Provider):
    display_name = "Oracle Cloud Infrastructure"
    resource_prefix = "oci"
    resources = PluginRegistry("%s.resources" % resource_prefix)
    resource_map = ResourceMap

    def initialize(self, options):
        return options

    def initialize_policies(self, policy_collection, options):
        return policy_collection

    def get_session_factory(self, options):
        return SessionFactory(profile=options['profile'])


resources = OCI.resources
