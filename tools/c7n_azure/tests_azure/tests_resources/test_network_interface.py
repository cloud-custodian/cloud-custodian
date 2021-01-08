# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
