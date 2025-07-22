# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from mock import patch, MagicMock
from .azure_common import BaseTest, arm_template


class ResourceLockFilter(BaseTest):

    def test_lock_filter_schema_validate(self):

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'resource-lock',
                 'lock-type': 'ReadOnly'}
            ]
        }, validate=True)
        self.assertTrue(p)

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'resource-lock'}
            ]
        }, validate=True)
        self.assertTrue(p)

    @patch('azure.mgmt.resource.locks.v2016_09_01.operations._operations.ManagementLocksOperations.list_at_resource_level')
    @patch('c7n_azure.resources.disk.Disk.augment', return_value=[{
        'id': '/subscriptions/.../resourceGroups/test/providers/Microsoft.Compute/disks/disk1',
        'name': 'disk1',
        'type': 'Microsoft.Compute/disks',
        'location': 'eastus',
        'properties': {},
        'resourceGroup': 'test'
    }])
    @arm_template('locked.json')
    def test_find_by_lock(self, mock_augment, mock_list_locks):
        # Simulate a lock being returned
        mock_lock = MagicMock()
        mock_lock.serialize.return_value = {'properties': {'level': 'CanNotDelete'}}
        mock_list_locks.return_value = [mock_lock]

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.disk',
            'filters': [
                {'type': 'resource-lock',
                 'lock-type': 'ReadOnly'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.disk',
            'filters': [
                {'type': 'resource-lock',
                 'lock-type': 'CanNotDelete'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @patch('azure.mgmt.resource.locks.v2016_09_01.operations._operations.ManagementLocksOperations.list_at_resource_level')
    @patch('c7n_azure.resources.disk.Disk.augment', return_value=[{
        'id': '/subscriptions/.../resourceGroups/test/providers/Microsoft.Compute/disks/disk1',
        'name': 'disk1',
        'type': 'Microsoft.Compute/disks',
        'location': 'eastus',
        'properties': {},
        'resourceGroup': 'test'
    }])
    @arm_template('locked.json')
    def test_find_by_lock_type_any(self, mock_augment, mock_list_locks):
        # Simulate a lock being returned (Any accepts all lock types)
        mock_lock = MagicMock()
        mock_lock.serialize.return_value = {'properties': {'level': 'CanNotDelete'}}
        mock_list_locks.return_value = [mock_lock]

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.disk',
            'filters': [
                {'type': 'resource-lock'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.disk',
            'filters': [
                {'type': 'resource-lock',
                 'lock-type': 'Any'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_find_by_lock_type_absent(self):
        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'resource-lock',
                 'lock-type': 'Absent'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
