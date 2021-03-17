# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from gcp_common import BaseTest


class InventoryTest(BaseTest):

    def test_instance_query(self):
        factory = self.replay_flight_data(
            'instance-asset-query',
            project_id='cloud-custodian'
        )
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
