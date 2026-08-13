# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os

from gcp_common import BaseTest

from c7n.config import Config
from c7n_gcp.query import config_regions
from c7n_gcp.region import Region


class ConfigRegionsTest(BaseTest):

    def test_no_explicit_region(self):
        # real gcp cli run with no --region: commands.py seeds
        # options.region = "" and, unlike aws, the gcp provider never
        # expands per-policy regions (GoogleCloud.initialize_policies is a
        # no-op), so config.region stays "".
        self.assertEqual(config_regions(Config.empty(region="")), ())

    def test_region_aws_default_sentinel(self):
        # Config.empty()'s own default region must not be treated as an
        # explicit gcp region, whether or not AWS_DEFAULT_REGION is set.
        default_region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
        self.assertEqual(config_regions(Config.empty(region=default_region)), ())

    def test_explicit_region(self):
        self.assertEqual(
            config_regions(Config.empty(region="us-central1")), ("us-central1",))

    def test_explicit_regions(self):
        self.assertEqual(
            config_regions(Config.empty(regions=("us-central1", "us-east1"))),
            ("us-central1", "us-east1"))

    def test_regions_all(self):
        self.assertEqual(config_regions(Config.empty(regions=("all",))), ())

    def test_regions_all_overrides_other_entries(self):
        self.assertEqual(
            config_regions(Config.empty(regions=("us-central1", "all"))), ())


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
