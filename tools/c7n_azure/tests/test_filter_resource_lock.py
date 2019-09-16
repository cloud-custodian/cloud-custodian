# Copyright 2019 Microsoft Corporation
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

from __future__ import absolute_import, division, print_function, unicode_literals
from azure_common import BaseTest, arm_template


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
