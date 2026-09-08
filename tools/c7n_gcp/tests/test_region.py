# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest

from c7n.config import Config
from c7n_gcp.region import Region


class RegionResourcesTest(BaseTest):

    def get_region(self, data=(), **config):
        ctx = self.get_context(config=Config.empty(**config))
        return Region(ctx, data)

    def test_no_explicit_region_enumerates_all(self):
        # A region-parented resource (e.g. dataproc-clusters) must still
        # enumerate its parent regions when no --region was given, rather
        # than collapsing to zero.
        region = self.get_region(region="")
        self.assertEqual(len(region.resources()), len(region.regions))

    def test_resource_ids(self):
        region = self.get_region()
        self.assertEqual(
            region.resources(resource_ids=('us-central1',)),
            [{'name': 'us-central1'}])

    def test_config_region(self):
        region = self.get_region(region="us-central1")
        self.assertEqual(region.resources(), [{'name': 'us-central1'}])

    def test_data_query(self):
        # RegionalResourceManager.get_parent_resource_query() resolves
        # config.regions/config.region into this 'query' form before
        # constructing the parent Region manager.
        region = self.get_region(data={'query': [{'name': 'us-central1'}]})
        self.assertEqual(region.resources(), [{'name': 'us-central1'}])
