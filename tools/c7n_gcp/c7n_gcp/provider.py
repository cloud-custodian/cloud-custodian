# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.registry import PluginRegistry
from c7n.provider import Provider, clouds

from .client import Session
from functools import partial

from c7n_gcp.resources.resource_map import ResourceMap


@clouds.register('gcp')
class GoogleCloud(Provider):

    display_name = 'GCP'
    resource_prefix = 'gcp'
    resources = PluginRegistry('%s.resources' % resource_prefix)
    resource_map = ResourceMap

    def initialize(self, options):
        return options

    def initialize_policies(self, policy_collection, options):
        return policy_collection

    def get_session_factory(self, options):
        """Get a credential/session factory for api usage."""
        return partial(
            Session, project_id=options.account_id, impersonate_service=options.assume_role)


resources = GoogleCloud.resources
