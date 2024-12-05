# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.resources import load_resources
from c7n_gcp.query import GcpLocation
from c7n_gcp.provider import GoogleCloud

from gcp_common import BaseTest


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
        'pubsub-snapshot',
        'region'
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
