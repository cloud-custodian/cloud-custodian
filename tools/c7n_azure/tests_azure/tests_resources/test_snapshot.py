# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class SnapshotTest(BaseTest):

    def test_find_by_name_and_delete(self):
        p = self.load_policy({
            'name': 'test-azure-snapshot',
            'resource': 'azure.snapshot',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'Testsnapshot'}],
            'actions': [
                {'type': 'delete'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        snapshot = resources.pop()
        client = p.resource_manager.get_client()
        current = client.snapshots.get(
            snapshot['resourceGroup'],
            snapshot['name']
        ).serialize(True)

        assert current['properties']['provisioningState'] == 'Deleting'
