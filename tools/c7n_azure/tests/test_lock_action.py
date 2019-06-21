# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from azure_common import BaseTest, arm_template
from jsonschema.exceptions import ValidationError


class LockActionTest(BaseTest):

    def test_valid_policy(self):
        policy = {
            'name': 'lock-cosmosdb',
            'resource': 'azure.cosmosdb',
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'ReadOnly'
                }
            ],
        }

        self.assertTrue(self.load_policy(data=policy, validate=True))

    def test_invalid_policy(self):
        # Missing lock-type parameter
        policy = {
            'name': 'lock-cosmosdb',
            'resource': 'azure.cosmosdb',
            'actions': [
                {
                    'type': 'lock'
                }
            ],
        }

        with self.assertRaises(ValidationError):
            self.load_policy(data=policy, validate=True)

    @arm_template('cosmosdb.json')
    def test_lock_action_resource(self):
        p = self.load_policy({
            'name': 'lock-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestcosmosdb'
                }
            ],
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'ReadOnly'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'resource-lock',
                 'lock-type': 'ReadOnly'}
            ]
        })
        resources = p.run()

        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_lock_action_resource_group(self):
        p = self.load_policy({
            'name': 'lock-cosmosdb-rg',
            'resource': 'azure.resourcegroup',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'test_cosmosdb'
                }
            ],
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'CanNotDelete'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.resourcegroup',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'test_cosmosdb'
                },
                {'type': 'resource-lock',
                 'lock-type': 'CanNotDelete'}
            ]
        })
        resources = p.run()

        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.cosmosdb',

            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestcosmosdb'
                },
                {'type': 'resource-lock',
                 'lock-type': 'CanNotDelete'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('sqlserver.json')
    def test_lock_action_child_resource(self):
        p = self.load_policy({
            'name': 'lock-sqldatabase',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestdb'
                }
            ],
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'CanNotDelete'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-lock-filter',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestdb'
                },
                {
                    'type': 'resource-lock',
                    'lock-type': 'CanNotDelete'
                }
            ]
        })
        resources = p.run()

        self.assertEqual(len(resources), 1)
