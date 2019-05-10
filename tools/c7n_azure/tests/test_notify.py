# Copyright 2015-2018 Capital One Services, LLC
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
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.session import Session


class NotifyTest(BaseTest):
    def setUp(self):
        super(NotifyTest, self).setUp()
        self.session = Session()

    def test_notify_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-notify-for-keyvault',
                'resource': 'azure.keyvault',
                'actions': [
                    {'type': 'notify',
                     'template': 'default',
                     'priority_header': '2',
                     'subject': 'testing notify action',
                     'to': ['user@domain.com'],
                     'transport':
                         {'type': 'asq',
                          'queue': ''}
                     }
                ]}, validate=True)
            self.assertTrue(p)

    @arm_template('keyvault.json')
    def test_notify_though_storage_queue(self):
        account = self.setup_account()

        # Create queue, make sure it is empty
        queue_url = "https://" + account.name + ".queue.core.windows.net/testnotify"
        queue, name = StorageUtilities.get_queue_client_by_uri(queue_url, self.session)
        queue.clear_messages(name)

        p = self.load_policy({
            'name': 'test-notify-for-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault1*'}],
            'actions': [
                {'type': 'notify',
                 'template': 'default',
                 'priority_header': '2',
                 'subject': 'testing notify action',
                 'to': ['user@domain.com'],
                 'transport':
                     {'type': 'asq',
                      'queue': queue_url}
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Pull messages, should be 1
        messages = StorageUtilities.get_queue_messages(queue, name)
        self.assertEqual(len(messages), 1)
