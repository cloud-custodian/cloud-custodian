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

from gcp_common import BaseTest


class LoadBalancingAddressTest(BaseTest):

    def test_loadbalancing_address_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('lb-addresses-query',
                                          project_id=project_id)
        p = self.load_policy(
            {'name': 'all-lb-addresses',
             'resource': 'gcp.loadbalancing-address'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'compute#address')
        self.assertEqual(resources[0]['address'], '35.193.10.19')

    def test_loadbalancing_address_get(self):
        factory = self.replay_flight_data('lb-addresses-get')
        p = self.load_policy(
            {'name': 'one-region-address',
             'resource': 'gcp.loadbalancing-address'},
            session_factory=factory)
        instance = p.resource_manager.get_resource(
            {'project': 'cloud-custodian',
             'address': 'new1',
             'region': 'us-central1'})
        self.assertEqual(instance['kind'], 'compute#address')
        self.assertEqual(instance['address'], '35.193.10.19')
