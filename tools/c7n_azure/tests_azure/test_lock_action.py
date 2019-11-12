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

from .azure_common import BaseTest, arm_template
from c7n_azure.utils import ResourceIdParser
from jsonschema.exceptions import ValidationError
from c7n_azure.session import Session

from c7n.utils import local_session


class LockActionTest(BaseTest):

    def setUp(self):
        super(LockActionTest, self).setUp()
        self.client = local_session(Session).client(
            'azure.mgmt.resource.locks.ManagementLockClient')
        self.resources = []

    def tearDown(self):
        if self.resources:
            self.assertEqual(len(self.resources), 1)
            resource = self.resources[0]
            if resource.get('resourceGroup') is None:
                self.client.management_locks.delete_at_resource_group_level(
                    resource['name'],
                    resource['lock'])
            else:
                self.client.management_locks.delete_by_scope(
                    resource['id'],
                    resource['lock']
                )

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

        policy_with_lock_fields = {
            'name': 'lock-cosmosdb',
            'resource': 'azure.cosmosdb',
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'ReadOnly',
                    'lock-name': 'testLock',
                    'lock-notes': 'testNotes'
                }
            ],
        }

        self.assertTrue(self.load_policy(data=policy_with_lock_fields, validate=True))

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
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestcosmosdb*'
                }
            ],
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'ReadOnly',
                    'lock-name': 'testLock',
                    'lock-notes': 'testNotes'
                }
            ],
        })
        self.resources = p.run()

        self.assertEqual(len(self.resources), 1)
        resource_name = self.resources[0]['name']
        self.assertTrue(resource_name.startswith('cctestcosmosdb'))

        locks = [r.serialize(True) for r in self.client.management_locks.list_at_resource_level(
            'test_cosmosdb',
            'Microsoft.DocumentDB',
            '',
            'databaseAccounts',
            resource_name)]

        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]['properties']['level'], 'ReadOnly')
        self.assertEqual(locks[0]['name'], 'testLock')
        self.assertEqual(locks[0]['properties']['notes'], 'testNotes')
        self.resources[0]['lock'] = locks[0]['name']

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
                    'lock-type': 'CanNotDelete',
                    'lock-name': 'testLock',
                    'lock-notes': 'testNotes'
                }
            ],
        })
        self.resources = p.run()
        self.assertEqual(len(self.resources), 1)
        self.assertEqual(self.resources[0]['name'], 'test_cosmosdb')

        locks = [r.serialize(True) for r in
                 self.client.management_locks.list_at_resource_group_level('test_cosmosdb')]

        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]['properties']['level'], 'CanNotDelete')
        self.assertEqual(locks[0]['name'], 'testLock')
        self.assertEqual(locks[0]['properties']['notes'], 'testNotes')
        self.resources[0]['lock'] = locks[0]['name']

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
                    'lock-type': 'CanNotDelete',
                    'lock-name': 'testLock',
                    'lock-notes': 'testNotes'
                }
            ],
        })
        self.resources = p.run()
        self.assertEqual(len(self.resources), 1)
        self.assertEqual(self.resources[0]['name'], 'cctestdb')

        locks = [r.serialize(True) for r in self.client.management_locks.list_at_resource_level(
            'test_sqlserver',
            'Microsoft.Sql/servers',
            ResourceIdParser.get_resource_name(self.resources[0]['c7n:parent-id']),
            'databases',
            'cctestdb')]

        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]['properties']['level'], 'CanNotDelete')
        self.assertEqual(locks[0]['name'], 'testLock')
        self.assertEqual(locks[0]['properties']['notes'], 'testNotes')
        self.resources[0]['lock'] = locks[0]['name']
