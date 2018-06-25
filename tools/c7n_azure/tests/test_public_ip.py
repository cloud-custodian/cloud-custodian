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
from mock import patch


class PublicIpAddressTest(BaseTest):
    def setUp(self):
        super(PublicIpAddressTest, self).setUp()

    @arm_template('vm.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'mypublicip'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    fake_public_ips = [
        {
            "name": "fake_name_1",
            "resourceGroup": "test_resource_group",
            "type": "Microsoft.Network/publicIPAddresses",
            "location": "southcentralus",
            "sku": {
                "name": "Basic"
            },
            "properties": {
                "publicIPAllocationMethod": "Dynamic",
                "publicIPAddressVersion": "IPv4",
                "ipConfiguration": {
                    "id": "Fake_loadbalancer_frontend_id_1"
                },
                "ipTags": [],
                "idleTimeoutInMinutes": 4,
                "resourceGuid": "fake_resourceGuid_1",
                "provisioningState": "Succeeded"
            },
            "etag": ""
        },
        {
            "name": "fake_name_2",
            "resourceGroup": "test_resource_group",
            "type": "Microsoft.Network/publicIPAddresses",
            "location": "southcentralus",
            "sku": {
                "name": "Basic"
            },
            "properties": {
                "publicIPAllocationMethod": "Dynamic",
                "publicIPAddressVersion": "IPv4",
                "ipConfiguration": {
                    "id": "Fake_loadbalancer_frontend_id_2"
                },
                "ipTags": [],
                "idleTimeoutInMinutes": 4,
                "resourceGuid": "fake_resourceGuid_2",
                "provisioningState": "Succeeded"
            },
            "etag": ""
        }
    ]

    @arm_template('vm.json')
    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_public_ips)
    @patch('c7n_azure.resources.public_ip.PublicIPDeleteAction.process',
        return_value=fake_public_ips)
    def test_delete_public_ip(self, delete_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'delete-public-ip',
            'resource': 'azure.publicip',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'fake_name_1'}],
            'actions': [
                {'type': 'delete'}]})
        p.run()
        delete_action_mock.assert_called_with([self.fake_public_ips[0]])
