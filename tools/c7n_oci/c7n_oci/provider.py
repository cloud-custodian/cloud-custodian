# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from functools import partial

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry
from c7n.utils import local_session
from .session import Session

from c7n_oci.resources.resource_map import ResourceMap

import logging

log = logging.getLogger("custodian.provider")


@clouds.register("oci")
class OCI(Provider):
    display_name = "Oracle Cloud Infrastructure"
    resource_prefix = "oci"
    resources = PluginRegistry("%s.resources" % resource_prefix)
    resource_map = ResourceMap

    def initialize(self, options):
        session = local_session(self.get_session_factory(options))
        session.initialize_session()
        options["oci_config"] = session.get_oci_config()
        return options

    def initialize_policies(self, policy_collection, options):
        return policy_collection

    def get_session_factory(self, options):
        return partial(Session)


resources = OCI.resources
