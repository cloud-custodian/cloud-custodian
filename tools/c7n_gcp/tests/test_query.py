# Copyright 2019 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from c7n_gcp.query import GcpLocation
from gcp_common import BaseTest


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
