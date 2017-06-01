# Copyright 2016 Capital One Services, LLC
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

from common import BaseTest, functional
from c7n.executor import MainThreadExecutor
from c7n.resources.glacier import Glacier

class GlacierTagTest(BaseTest):

    @functional
    def test_glacier_tag(self):
        session_factory = self.replay_flight_data('test_glacier_tag')
        client = session_factory().client('glacier')
        name = 'c7n-glacier-test'

        client.create_vault(vaultName=name)
        self.addCleanup(client.delete_vault, vaultName=name)

        p = self.load_policy({
            'name': 'glacier',
            'resource': 'glacier',
            'filters': [
                {
                    'type': 'value',
                    'key': 'VaultName',
                    'value': 'c7n-glacier-test'
                }
            ],
            'actions': [
                {
                    'type': 'tag',
                    'key': 'abc',
                    'value': 'xyz'
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['VaultName'], name)

        tags = client.list_tags_for_vault(vaultName=resources[0]['VaultName'])
        self.assertEqual(len(tags['Tags']), 1)
        self.assertTrue('abc' in tags['Tags'])

    def test_glacier_untag(self):
        session_factory = self.replay_flight_data('test_glacier_untag')
        client = session_factory().client('glacier')

        p = self.load_policy({
            'name': 'glacier',
            'resource': 'glacier',
            'filters': [
                {
                    'tag:abc': 'present'
                }
            ],
            'actions': [
                {
                    'type': 'remove-tag',
                    'tags': ['abc']
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_vault(vaultName=resources[0]['VaultName'])
        self.assertEqual(len(tags['Tags']), 0)

    def test_glacier_markop(self):
        session_factory = self.replay_flight_data('test_glacier_markop')
        client = session_factory().client('glacier')
        name = 'c7n-glacier-test'

        p = self.load_policy({
            'name': 'glacier',
            'resource': 'glacier',
            'filters': [
                {
                    'tag:abc': 'present'
                }
            ],
            'actions': [
                {
                    'type': 'mark-for-op',
                    'op': 'notify',
                    'days': 4
                }
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_vault(vaultName=resources[0]['VaultName'])
        self.assertEqual(len(tags['Tags']), 2)
        self.assertTrue('maid_status' in tags['Tags'])
