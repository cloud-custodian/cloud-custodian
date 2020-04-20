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
from ..azure_common import BaseTest, arm_template, requires_arm_polling


@requires_arm_polling
class NetworkInterfaceTest(BaseTest):
    def setUp(self):
        super(NetworkInterfaceTest, self).setUp()

    def test_network_interface_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-network-interface',
                'resource': 'azure.networkinterface'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('network_interface.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-network-interface',
            'resource': 'azure.networkinterface',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctestnic'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('vm.json')
    def test_find_by_default_routes(self):
        p = self.load_policy({
            'name': 'test-azure-network-interface',
            'resource': 'azure.networkinterface',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'myvmnic'},
                {'type': 'effective-route-table',
                 'key': 'routes.value[].nextHopType',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': 'VnetLocal'}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
