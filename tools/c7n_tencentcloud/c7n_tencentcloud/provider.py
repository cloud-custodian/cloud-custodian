# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import logging
from .client import Session

from c7n.registry import PluginRegistry
from c7n.provider import Provider, clouds
from c7n.policy import PolicyCollection
from c7n_tencentcloud.resources.resource_map import ResourceMap


DEFAULT_REGION = "ap-singapore"


log = logging.getLogger("custodian.tencentcloud")


@clouds.register("tencentcloud")
class TencentCloud(Provider):
    """
    tencent cloud provider
    """
    display_name = "Tencent Cloud"
    resource_prefix = "tencentcloud"
    resources: PluginRegistry = PluginRegistry(f"{resource_prefix}.resources")
    resource_map = ResourceMap

    def initialize(self, options):
        """
        It takes a dictionary of options, do some update work and return it

        :param options: A dictionary of options
        :return: The options are being returned.
        """
        # support --region option
        # when set multi regions, only the first one will be used
        if len(options.regions) == 0:
            options.region = os.environ.get("TENCENTCLOUD_REGION", DEFAULT_REGION)
        else:
            options.region = options.regions[0]
        if not options.account_id:
            session = self.get_session_factory(options)
            options.account_id = session().client(
                endpoint='sts.tencentcloudapi.com',
                service='sts',
                version='2018-08-13',
                region=options.region
            ).execute_query("GetCallerIdentity", {}).get('AccountId')
        return options

    def initialize_policies(self, policy_collection: PolicyCollection, options: dict):
        """
        This function is called when the policy collection is initialized

        :param policy_collection: This is the collection of policies
        :type policy_collection: PolicyCollection
        :param options: A dictionary of options that can be used to configure the policy
        :type options: dict
        :return: The policy collection.
        """
        return policy_collection

    def get_session_factory(self, options):
        """
        The function returns a session factory

        :param options: A dictionary of options that are passed to the session factory
        :return: A session factory
        """
        profile = getattr(options, 'profile', None)
        return lambda: Session(profile_name=profile)


resources = TencentCloud.resources
