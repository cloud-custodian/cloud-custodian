# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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

    @arm_template('locked.json')
    def test_find_by_lock(self):
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

    @arm_template('locked.json')
    def test_find_by_lock_type_any(self):

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
