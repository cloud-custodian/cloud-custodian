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

from azure_common import BaseTest
from c7n_azure.utils import get_service_tag_ip_space
from unittest import mock
import json


class UtilsTest(BaseTest):

    @mock.patch('azure.mgmt.network._network_management_client.NetworkManagementClient')
    def test_get_service_tag_ip_space(self, client_mock):
        client_mock.service_tags = mock.MagicMock()
        client_mock.service_tags.list.return_value = UtilsTest.get_ip_space()

        result = get_service_tag_ip_space('ApiManagement', 'WestUS')
        self.assertEqual(10, len(result))

        # This is in all regions, so it must be larger than previous
        result = get_service_tag_ip_space('ApiManagement')
        self.assertEqual(10, len(result))


    @staticmethod
    def get_ip_space():
        data = """
           { "values": [
                {
                    "name": "ApiManagement",
                    "id": "ApiManagement",
                    "properties": {
                        "address_prefixes": [
                            "13.69.64.76/31",
                            "13.69.66.144/28",
                            "23.101.67.140/32",
                            "51.145.179.78/32",
                            "137.117.160.56/32"
                        ]
                    }
                },
                {
                    "name": "ApiManagement.WestUS",
                    "id": "ApiManagement.WestUS",
                    "properties": {
                        "address_prefixes": [
                            "13.64.39.16/32",
                            "40.112.242.148/31",
                            "40.112.243.240/28"
                        ]
                    }
                }
            ]
         }"""

        return json.loads(data)

