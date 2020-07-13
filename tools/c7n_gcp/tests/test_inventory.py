# Copyright 2020 Kapil Thangavelu
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


class InventoryTest(BaseTest):

    def test_instance_query(self):
        factory = self.replay_flight_data('instance-asset-query')
        inventory = self.load_policy(
            {'name': 'fetch',
             'source': 'inventory',
             'resource': 'gcp.instance'},
            session_factory=factory)
        describe = self.load_policy(
            {'name': 'fetch',
             'resource': 'gcp.instance'},
            session_factory=factory)

        results = inventory.resource_manager.resources()
        assert len(results) == 1
        inventory_instance = results.pop()

        results = describe.resource_manager.resources()
        assert len(results) == 1
        describe_instance = results.pop()

        # couple of super minors on deltas on describe, mostly fingerprint
        # and kinds in the describe are mangled or removed as redundant in
        # the asset inventory.
        delta = ('allocationAffinity', 'fingerprint', 'c7n:history',
                 'kind', 'metadata', 'reservationAffinity')
        for d in delta:
            inventory_instance.pop(d, None)
            describe_instance.pop(d, None)
        for nic in inventory_instance['networkInterfaces']:
            nic.pop('fingerprint')
        for nic in describe_instance['networkInterfaces']:
            nic.pop('kind')
            nic.pop('fingerprint')
            nic['accessConfigs'][0].pop('kind')
        for disk in describe_instance['disks']:
            disk.pop('kind')
        assert inventory_instance == describe_instance
