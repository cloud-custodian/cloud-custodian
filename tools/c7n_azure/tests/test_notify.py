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


class NotifyTest(BaseTest):
    def setUp(self):
        super(NotifyTest, self).setUp()

    @arm_template('keyvault.json')
    def test_notify_though_storage_queue(self):
        account = self.setup_account()
        queue_url = "https://" + account.name + ".queue.core.windows.net/testcc"
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
                      'queue': queue_url}
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
