# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_azure.resources.apimanagement import Resize
from unittest.mock import MagicMock

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

    def test_certificates_filter(self):
        p = self.load_policy({
            'name': 'cert',
            'resource': 'azure.api-management',
            'filters': [{
                'type': 'certificates',
                'count': 1,
                'count_op': 'gte'
            }]
        })
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('vvapimgmt1', resources[0]['name'])
