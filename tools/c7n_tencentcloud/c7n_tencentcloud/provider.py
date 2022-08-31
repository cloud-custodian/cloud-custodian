# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .client import Session

from c7n.registry import PluginRegistry
from c7n.provider import Provider, clouds
from c7n.policy import PolicyCollection
from c7n_tencentcloud.resources.resource_map import ResourceMap


DEFAULT_REGION = "ap-singapore"


@clouds.register("tencentcloud")
class TencentCloud(Provider):
    """
    tencent cloud provider
    """
    display_name = "Tencent Cloud"
    resource_prefix = "tencentcloud"
    resources: PluginRegistry = PluginRegistry(f"{resource_prefix}.resources")
    resource_map = ResourceMap

    def initialize(self, options: dict) -> dict:
        """
        > It takes a dictionary of options, do some update work and return it

        :param options: A dictionary of options
        :return: The options are being returned.
        """
        # support --region option
        # when set multi regions, only the first one will be used
        if not options.regions:
            options.region = DEFAULT_REGION
        else:
            options.region = options.regions[0]
        return options

    def initialize_policies(self, policy_collection: PolicyCollection, options: dict):
        """
        > This function is called when the policy collection is initialized

        :param policy_collection: This is the collection of policies
        :type policy_collection: PolicyCollection
        :param options: A dictionary of options that can be used to configure the policy
        :type options: dict
        :return: The policy collection.
        """
        return policy_collection

    def get_session_factory(self, options):
        """
        > The function returns a session factory

        :param options: A dictionary of options that are passed to the session factory
        :return: A session object.
        """
        return Session()


resources = TencentCloud.resources
