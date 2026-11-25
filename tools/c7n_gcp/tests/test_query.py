# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os

from datetime import datetime, timedelta

from c7n.config import Config
from c7n.resources import load_resources
from c7n_gcp.query import config_regions, GcpLocation
from c7n_gcp.provider import GoogleCloud

from gcp_common import BaseTest


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


def test_gcp_resource_metadata_asset_type():
    load_resources(('gcp.*',))
    # asset inventory doesn't support these
    whitelist = set((
        'app-engine-domain',
        'app-engine-certificate',
        'app-engine-firewall-ingress-rule',
        'app-engine-domain-mapping',
        'bigtable-instance-table',
        'bigtable-instance-cluster-backup',
        'bigtable-instance',
        'bigtable-instance-cluster',
        'artifact-repository',
        'bq-job',
        'bq-project',
        'build',
        'dataflow-job',
        'dm-deployment',
        'datafusion-instance',
        'instance-group-manager',
        'secret',
        'function',
        'loadbalancer-ssl-policy',
        'log-exclusion',
        'ml-job',
        'ml-model',
        'notebook',
        'patch-deployment',
        'sourcerepo',
        'sql-backup-run',
        'sql-ssl-cert',
        'sql-user',
        'firestore-backup-schedule',
        'firestore-field',
        'firestore-index',
        'pubsub-snapshot',
        'region',
        'vertex-ai-publisher',  # Synthetic resource (no asset inventory type)
        'vertex-ai-publisher-model',  # Catalog resource (no asset inventory type)
        'vertex-ai-location',
        'workspace-user',  # not a GCP resource (no asset inventory type)
        'vertex-ai-evaluation-run',  # No asset inventory type yet
        'vertex-ai-metadata-store-artifact',  # Not tracked by asset inventory
    ))
    missing = set()
    for k, v in GoogleCloud.resources.items():
        if v.resource_type.asset_type is None:
            missing.add(k)
    remainder = missing.difference(whitelist)
    if remainder:
        raise ValueError(str(remainder))


class GcpLocationTest(BaseTest):
    _app_locations = ["asia-east2",
                      "asia-northeast1",
                      "asia-northeast2",
                      "asia-south1",
                      "australia-southeast1",
                      "europe-west",
                      "europe-west2",
                      "europe-west3",
                      "europe-west6",
                      "northamerica-northeast1",
                      "southamerica-east1",
                      "us-central",
                      "us-east1",
                      "us-east4",
                      "us-west2"]

    _kms_locations = ["asia",
                      "asia-east1",
                      "asia-east2",
                      "asia-northeast1",
                      "asia-northeast2",
                      "asia-south1",
                      "asia-southeast1",
                      "australia-southeast1",
                      "eur4",
                      "europe",
                      "europe-north1",
                      "europe-west1",
                      "europe-west2",
                      "europe-west3",
                      "europe-west4",
                      "europe-west6",
                      "global",
                      "nam4",
                      "northamerica-northeast1",
                      "southamerica-east1",
                      "us",
                      "us-central1",
                      "us-east1",
                      "us-east4",
                      "us-west1",
                      "us-west2"]

    def test_locations_combined(self):
        combined_locations = {}

        for location in self._app_locations:
            services = ['appengine']
            if location in self._kms_locations:
                services.append('kms')
            combined_locations[location] = services

        for location in self._kms_locations:
            if location not in self._app_locations:
                combined_locations[location] = ['kms']

        self.assertEqual(GcpLocation._locations, combined_locations)

    def test_locations_appengine(self):
        self._test_locations_by_service(self._app_locations, 'appengine')

    def test_locations_kms(self):
        self._test_locations_by_service(self._kms_locations, 'kms')

    def _test_locations_by_service(self, locations, service_name):
        locations_set = set(locations)
        actual_locations_set = set(GcpLocation.get_service_locations(service_name))
        self.assertTrue(locations_set.issubset(actual_locations_set))
        self.assertTrue(actual_locations_set.issubset(locations_set))


class GcpMetricsFilterTest(BaseTest):
    def setUp(self):
        # Ensure everything has been populated/loaded.
        load_resources(('gcp.*',))
        return super().setUp()

    def get_resource_by_name(self, name):
        for k, v in GoogleCloud.resources.items():
            if k == name:
                return v

        raise ValueError(f"No resource found for name: {name}")

    def test_metrics_autoregistered(self):
        SpannerInstance = self.get_resource_by_name("spanner-instance")
        # Sanity check to ensure it is auto-registering metrics filters.
        self.assertTrue(SpannerInstance.resource_type.allow_metrics_filters)
        # Ensure the metrics got registered correctly.
        self.assertTrue("metrics" in SpannerInstance.filter_registry)

    def test_metrics_not_registered(self):
        SpannerDatabaseInstance = self.get_resource_by_name("spanner-database-instance")
        # Sanity check to ensure it is NOT auto-registering metrics filters.
        self.assertFalse(SpannerDatabaseInstance.resource_type.allow_metrics_filters)
        # Ensure the metrics were NOT registered.
        self.assertFalse("metrics" in SpannerDatabaseInstance.filter_registry)


def test_date_renders_in_the_shape_the_api_returns(test):
    # google apis return rfc 3339, and a value filter compares those as plain
    # strings. a space separated datetime sorts below every time on the same
    # day, because a space sorts below the "T", so without the provider format
    # this silently matches records older than the cutoff.
    policy = test.load_policy({
        'name': 'recent-custom-jobs',
        'resource': 'gcp.vertex-ai-custom-job',
        'filters': [{'type': 'value', 'key': 'createTime',
                     'op': 'greater-than', 'value': '{now:-90d}'}]})
    # bracket the expansion, so a run crossing utc midnight isn't a failure
    before = datetime.utcnow()
    policy.expand_variables(policy.get_variables())
    after = datetime.utcnow()

    cutoff = policy.data['filters'][0]['value']
    # strptime pins the whole shape, not just the ends, so a format that drops
    # the Z or the colons or fixes the time at midnight fails here
    rendered = datetime.strptime(cutoff, '%Y-%m-%dT%H:%M:%SZ')
    # bracket on real timestamps, so a run crossing utc midnight isn't a
    # failure. strftime truncates the microseconds rather than rounding.
    assert (before.replace(microsecond=0) - timedelta(days=90)
            <= rendered
            <= after.replace(microsecond=0) - timedelta(days=90)), cutoff

    # midnight on the cutoff day is at or before the cutoff either way, so an
    # older job must not match. it does when the cutoff carries a space.
    older = {'createTime': f'{cutoff[:10]}T00:00:00Z'}
    value_filter = policy.resource_manager.filters[0]
    value_filter.annotate = False
    assert not value_filter(older), (cutoff, older)


def test_date_explicit_format_wins(test):
    # a policy that wants something else still gets it
    policy = test.load_policy({
        'name': 'recent-custom-jobs',
        'resource': 'gcp.vertex-ai-custom-job',
        'filters': [{'type': 'value', 'key': 'createTime',
                     'op': 'greater-than', 'value': '{now:-90d%Y-%m-%d}'}]})
    before = datetime.utcnow()
    policy.expand_variables(policy.get_variables())
    after = datetime.utcnow()

    days = {(t - timedelta(days=90)).strftime('%Y-%m-%d') for t in (before, after)}
    assert policy.data['filters'][0]['value'] in days
