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

from azure_common import BaseTest, arm_template, cassette_name
from c7n_azure.storage_utils import StorageUtilities
from mock import patch
from c7n_azure.session import Session
from c7n_azure.utils import local_session


class StorageContainerTest(BaseTest):
    def setUp(self):
        super(StorageContainerTest, self).setUp()
        StorageUtilities.get_storage_primary_key.cache_clear()

    def test_storage_schema_validate(self):
        p = self.load_policy({
            'name': 'test-storage-container',
            'resource': 'azure.storage-container'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('storage.json')
    @cassette_name('containers')
    def test_value_filter(self):
        p = self.load_policy({
            'name': 'test-azure-storage-container-enum',
            'resource': 'azure.storage-container',
            'filters': [
                {'type': 'parent',
                 'filter':
                    {'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value_type': 'normalize',
                     'value': 'cctstorage*'}}],
        })
        resources = p.run()
        self.assertEqual(2, len(resources))
        self.assertEqual({'containerone', 'containertwo'}, set([c['name'] for c in resources]))

    @arm_template('storage.json')
    @cassette_name('containers')
    def test_set_public_access(self):
        with patch('azure.mgmt.storage.v%s.operations.'
        'BlobContainersOperations.update'
        % self._get_storage_management_client_api_string()) as update_container_mock:
            p = self.load_policy({
                'name': 'test-azure-storage-container-enum',
                'resource': 'azure.storage-container',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name',
                        'value': 'containerone'
                    }
                ],
                'actions': [
                    {
                        'type': 'set-public-access',
                        'value': 'None'
                    }
                ]
            }, validate=True)

            p.run()
            args, kwargs = update_container_mock.call_args_list[0]
            self.assertEqual('test_storage', args[0])
            self.assertTrue(args[1].startswith('cctstorage'))
            self.assertEqual('None', kwargs['public_access'])

    def _get_storage_management_client_api_string(self):
        return local_session(Session)\
            .client('azure.mgmt.storage.StorageManagementClient')\
            .DEFAULT_API_VERSION.replace("-", "_")
