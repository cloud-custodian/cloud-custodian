# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from functools import partial

from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry
from c7n.resolver import URIResolver
from c7n.utils import local_session
from .session import Session

from c7n_azure.resources.resource_map import ResourceMap
from c7n_azure.resolver import resolve_azure_blob
from msrestazure.azure_cloud import (AZURE_CHINA_CLOUD, AZURE_GERMAN_CLOUD, AZURE_PUBLIC_CLOUD,
                                     AZURE_US_GOV_CLOUD)
import logging
import sys

log = logging.getLogger('custodian.provider')


@clouds.register('azure')
class Azure(Provider):

    display_name = 'Azure'
    resource_prefix = 'azure'
    resources = PluginRegistry('%s.resources' % resource_prefix)
    resource_map = ResourceMap
    region_to_cloud = {
        'AzureCloud': AZURE_PUBLIC_CLOUD,
        'AzureChinaCloud': AZURE_CHINA_CLOUD,
        'AzureGermanCloud': AZURE_GERMAN_CLOUD,
        'AzureUSGovernment': AZURE_US_GOV_CLOUD
    }

    cloud_endpoints = None

    def initialize(self, options):
        self.cloud_endpoints = self._get_cloud_endpoints(options)
        options['region'] = self.cloud_endpoints.name

        if options['account_id'] is None:
            session = local_session(self.get_session_factory(options))
            options['account_id'] = session.get_subscription_id()
        options['cache'] = 'memory'
        return options

    def initialize_policies(self, policy_collection, options):
        return policy_collection

    def get_session_factory(self, options):
        cloud_endpoint = self.cloud_endpoints

        # c7n-org will have a region set to either global or the specified region
        region = options.get('region')
        if region:
            cloud_endpoint = self.region_to_cloud.get(region, AZURE_PUBLIC_CLOUD)

        return partial(Session,
                       subscription_id=options.account_id,
                       authorization_file=options.authorization_file,
                       cloud_endpoints=cloud_endpoint)

    def _get_cloud_endpoints(self, options):
        cloud_list = options.get('regions')

        if not cloud_list:
            return AZURE_PUBLIC_CLOUD
        elif len(cloud_list) > 1:
            log.error('Multiple Azure Clouds provided. Please pass in only one.')
            sys.exit(1)

        # Only support passing in one cloud at a time
        cloud = self.region_to_cloud.get(cloud_list[0])

        if cloud:
            return cloud
        else:
            log.error('Region Flag: %s not recognized. Available values: %s.',
                      cloud_list[0], ", ".join(self.region_to_cloud.keys()))
            sys.exit(1)


resources = Azure.resources

# Register the azure:// URI scheme handler with the core resolver
URIResolver.register_provider('azure', resolve_azure_blob)
