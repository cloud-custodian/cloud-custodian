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
from c7n_azure.resources.apimanagement import Resize
from mock import MagicMock

from ..azure_common import BaseTest, arm_template

from c7n.utils import local_session
from c7n_azure.session import Session


class ApiManagementTest(BaseTest):
    def setUp(self):
        super(ApiManagementTest, self).setUp()

    def test_apimanagement_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-apimanagement',
                'resource': 'azure.api-management'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('apimanagement.json')
    def test_find_apimanagement_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-apimanagement',
            'resource': 'azure.api-management',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestapimanagement*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_resize_action(self):
        action = Resize(data={'capacity': 8, 'tier': 'Premium'})
        action.client = MagicMock()
        action.manager = MagicMock()
        action.session = local_session(Session)

        resource = {
            'id': '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/test-rg/'
                  'providers/Microsoft.ApiManagement/service/test-apimanagement',
            'name': 'test-apimanagement',
            'type': 'Microsoft.ApiManagement/service',
            'sku': {'name': 'Developer', 'capacity': 1, 'tier': 'Developer'},
            'resourceGroup': 'test-rg'
        }

        action.process([resource])

        update_by_id = action.client.resources.update_by_id

        self.assertEqual(len(update_by_id.call_args_list), 1)
        self.assertEqual(len(update_by_id.call_args_list[0][0]), 3)
        self.assertEqual(update_by_id.call_args_list[0][0][2].serialize()['sku']['capacity'], 8)
        self.assertEqual(update_by_id.call_args_list[0][0][2].serialize()['sku']['tier'], 'Premium')
