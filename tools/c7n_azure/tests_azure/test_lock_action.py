# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
from c7n_azure.session import Session

from c7n.exceptions import PolicyValidationError
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
        super(LockActionTest, self).tearDown()

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

        with self.assertRaises(PolicyValidationError):
            self.load_policy(data=policy, validate=True)

    @arm_template('locked.json')
    def test_lock_action_resource(self):
        p = self.load_policy({
            'name': 'lock-sqlserver',
            'resource': 'azure.sqlserver',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value': 'cclockedsqlserver*'
                }
            ],
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'ReadOnly',
                    'lock-name': 'sqllock',
                    'lock-notes': 'testNotes'
                }
            ],
        })
        self.resources = p.run()

        self.assertEqual(len(self.resources), 1)
        resource_name = self.resources[0]['name']
        self.assertTrue(resource_name.startswith('cclockedsqlserver'))

        locks = [r.serialize(True)
                 for r in self.client.management_locks.list_by_scope(self.resources[0]['id'])
                 if r.name == 'sqllock']

        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]['properties']['level'], 'ReadOnly')
        self.assertEqual(locks[0]['properties']['notes'], 'testNotes')
        self.resources[0]['lock'] = locks[0]['name']

    @arm_template('locked.json')
    def test_lock_action_resource_group(self):
        p = self.load_policy({
            'name': 'lock-locked-rg',
            'resource': 'azure.resourcegroup',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'test_locked'
                }
            ],
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'CanNotDelete',
                    'lock-name': 'rglock',
                    'lock-notes': 'testNotes'
                }
            ],
        })
        self.resources = p.run()
        self.assertEqual(len(self.resources), 1)
        self.assertEqual(self.resources[0]['name'], 'test_locked')

        locks = [r.serialize(True) for r in
                 self.client.management_locks.list_at_resource_group_level('test_locked')
                 if r.name == 'rglock']

        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]['properties']['level'], 'CanNotDelete')
        self.assertEqual(locks[0]['properties']['notes'], 'testNotes')
        self.resources[0]['lock'] = locks[0]['name']

    @arm_template('locked.json')
    def test_lock_action_child_resource(self):
        p = self.load_policy({
            'name': 'lock-sqldatabase',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cclockeddb'
                }
            ],
            'actions': [
                {
                    'type': 'lock',
                    'lock-type': 'ReadOnly',
                    'lock-name': 'dblock',
                    'lock-notes': 'testNotes'
                }
            ],
        })
        self.resources = p.run()
        self.assertEqual(len(self.resources), 1)
        self.assertEqual(self.resources[0]['name'], 'cclockeddb')

        locks = [r.serialize(True) for r in self.client.management_locks.list_at_resource_level(
            'test_locked',
            'Microsoft.Sql/servers',
            ResourceIdParser.get_resource_name(self.resources[0]['c7n:parent-id']),
            'databases',
            'cclockeddb') if r.name == 'dblock']

        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]['properties']['level'], 'ReadOnly')
        self.assertEqual(locks[0]['properties']['notes'], 'testNotes')
        self.resources[0]['lock'] = locks[0]['name']
