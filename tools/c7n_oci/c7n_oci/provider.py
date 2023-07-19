# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n_oci.resources.resource_map import ResourceMap
import copy
from urllib import parse as urlparse

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry

from .session import SessionFactory

log = logging.getLogger("custodian.provider")
_oci_profile_session = None


def get_oci_profile_session(options):
    if _oci_profile_session:
        return _oci_profile_session
    else:
        session_factory = SessionFactory()
        return session_factory()


def join_output(output_dir, suffix):
    if "{region}" in output_dir:
        return output_dir.rstrip("/")
    if output_dir.endswith("://"):
        return output_dir + suffix
    output_url_parts = urlparse.urlparse(output_dir)
    # for output urls, the end of the url may be a
    # query string. make sure we add a suffix to
    # the path component.
    output_url_parts = output_url_parts._replace(
        path=output_url_parts.path.rstrip("/") + "/%s" % suffix
    )
    return urlparse.urlunparse(output_url_parts)


@clouds.register("oci")
class OCI(Provider):
    display_name = "Oracle Cloud Infrastructure"
    resource_prefix = "oci"
    resources = PluginRegistry("%s.resources" % resource_prefix)
    resource_map = ResourceMap

    def initialize(self, options):
        if options["account_id"] is None:
            options["oci_config"] = get_oci_profile_session(options).get_config()
        return options

    def _get_subscribed_region(self, options):
        client = get_oci_profile_session(options).client("oci.identity.IdentityClient")
        return client.list_region_subscriptions(tenancy_id=options["oci_config"]["tenancy"]).data

    def _is_subscribed_region(self, subscribed_regions, region, policy_collection):
        for r in subscribed_regions:
            if r.region_name == region and r.status == "READY":
                return True

        policy_collection.log.info(
            (
                "User's tenancy is not subscribed to the %s region. "
                "So skipping this region for the policy execution."
            ),
            region,
        )
        return False

    def initialize_policies(self, policy_collection, options):
        from c7n.policy import Policy, PolicyCollection

        if options.regions:
            policies = []
            subscribed_regions = self._get_subscribed_region(options)
            if "all" in options.regions:
                regions = [r.region_name for r in subscribed_regions]
            else:
                regions = [
                    r
                    for r in options.regions
                    if self._is_subscribed_region(subscribed_regions, r, policy_collection)
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
                            session_factory=policy_collection.session_factory(),
                        )
                    )
            return PolicyCollection(policies, options)

        return policy_collection

    def get_session_factory(self, options):
        global _oci_profile_session
        session_factory = SessionFactory(profile=options["profile"], region=options["region"])
        _oci_profile_session = session_factory()
        return session_factory


resources = OCI.resources
