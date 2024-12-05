# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template, cassette_name, DEFAULT_SUBSCRIPTION_ID
from c7n_azure.storage_utils import StorageUtilities
from mock import patch
from c7n_azure.constants import CONTAINER_EVENT_TRIGGER_MODE
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
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'container*'},
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
        self.assertEqual({'containerone', 'containertwo'}, {c['name'] for c in resources})

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
            args, _ = update_container_mock.call_args_list[0]
            self.assertEqual('test_storage', args[0])
            self.assertTrue(args[1].startswith('cctstorage'))
            self.assertEqual('containerone', args[2])
            self.assertEqual('None', args[3].public_access)

    @arm_template('storage.json')
    def test_event(self):
        p = self.load_policy({
            'name': 'test-azure-container-event',
            'mode':
                {'type': CONTAINER_EVENT_TRIGGER_MODE,
                 'events': ['StorageContainerWrite']},
            'resource': 'azure.storage-container'})

        account = self.setup_account()

        event = {"subject": "/subscriptions/" + DEFAULT_SUBSCRIPTION_ID + "/resourceGroups/"
                            "test_storage/providers/Microsoft.Storage/storageAccounts"
                            "/" + account.name + "/blobServices/default/containers/containerone",
                "eventTime": "2019-07-16T18:30:43.3595255Z",
                "id": "619d2674-b396-4356-9619-6c5a52fe4e88"}

        resources = p.push(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'containerone')

    def _get_storage_management_client_api_string(self):
        return local_session(Session)\
            .client('azure.mgmt.storage.StorageManagementClient')\
            .DEFAULT_API_VERSION.replace("-", "_")
