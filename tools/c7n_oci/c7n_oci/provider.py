# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n_oci.resources.resource_map import ResourceMap
import copy

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry

from c7n_oci.utils import join_output
from .session import SessionFactory

log = logging.getLogger("custodian.oci.provider")


@clouds.register("oci")
class OCI(Provider):
    display_name = "Oracle Cloud Infrastructure"
    resource_prefix = "oci"
    resources = PluginRegistry("%s.resources" % resource_prefix)
    resource_map = ResourceMap
    _oci_profile_session = None

    def initialize(self, options):
        if options["account_id"] is None:
            options["oci_config"] = self._get_oci_profile_session(options).get_config()
        return options

    def _get_subscribed_regions(self, options):
        client = self._get_oci_profile_session(options).client("oci.identity.IdentityClient")
        subscribed_regions = client.list_region_subscriptions(
            tenancy_id=options["oci_config"]["tenancy"]
        ).data
        regions = [region.region_name for region in subscribed_regions if region.status == "READY"]
        return regions

    @staticmethod
    def _is_subscribed_region(subscribed_regions, region):
        if region in subscribed_regions:
            return True

        log.info(
            (
                "User's tenancy is not subscribed to the %s region. "
                "So skipping this region for the policy execution."
            ),
            region,
        )
        return False

    def _get_oci_profile_session(self, options):
        if self._oci_profile_session is None:
            self._oci_profile_session = self.get_session_factory(options)()
        return self._oci_profile_session

    def initialize_policies(self, policy_collection, options):
        from c7n.policy import Policy, PolicyCollection

        if not options.regions:
            return policy_collection
        policies = []
        subscribed_regions = self._get_subscribed_regions(options)
        if "all" in options.regions:
            # TODO: Check whether the service used in the policy is supported in
            # the subscribed regions to avoid the failures during the execution
            regions = subscribed_regions
        else:
            regions = [
                r for r in options.regions if self._is_subscribed_region(subscribed_regions, r)
            ]
        for p in policy_collection:
            for region in regions:
                options_copy = copy.copy(options)
                options_copy.region = str(region)
                if (
                    len(options.regions) > 1
                    or "all" in options.regions
                    and getattr(options, "output_dir", None)
                ):
                    options_copy.output_dir = join_output(options.output_dir, region)
                policies.append(
                    Policy(
                        p.data,
                        options_copy,
                        session_factory=self.get_session_factory(options_copy),
                    )
                )
        return PolicyCollection(policies, options)

    def get_session_factory(self, options):
        session_factory = SessionFactory(profile=options["profile"], region=options["region"])
        return session_factory


resources = OCI.resources
