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


class VMTest(BaseTest):
    def setUp(self):
        super(VMTest, self).setUp()

    @arm_template('vm.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('vm.json')
    def test_find_running(self):
        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'instance-view',
                 'key': 'statuses[].code',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': 'PowerState/running'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    fake_running_vms = [{
        'resourceGroup': 'test_resource_group',
        'name': 'test_vm'
    }]

    @arm_template('vm.json')
    @patch('c7n_azure.resources.vm.InstanceViewFilter.process', return_value=fake_running_vms)
    @patch('c7n_azure.resources.vm.VmStopAction.stop')
    def test_stop(self, stop_action_mock, filter_mock):

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'instance-view',
                 'key': 'statuses[].code',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': 'PowerState/running'}],
            'actions': [
                {'type': 'stop'}
            ]
        })
        p.run()
        stop_action_mock.assert_called_with(
            self.fake_running_vms[0]['resourceGroup'],
            self.fake_running_vms[0]['name'])

    @arm_template('vm.json')
    @patch('c7n_azure.resources.vm.InstanceViewFilter.process', return_value=fake_running_vms)
    @patch('c7n_azure.resources.vm.VmPowerOffAction.poweroff')
    def test_poweroff(self, poweroff_action_mock, filter_mock):

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'instance-view',
                 'key': 'statuses[].code',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': 'PowerState/running'}],
            'actions': [
                {'type': 'poweroff'}
            ]
        })
        p.run()
        poweroff_action_mock.assert_called_with(
            self.fake_running_vms[0]['resourceGroup'],
            self.fake_running_vms[0]['name'])

    @arm_template('vm.json')
    @patch('c7n_azure.resources.vm.InstanceViewFilter.process', return_value=fake_running_vms)
    @patch('c7n_azure.resources.vm.VmStartAction.start')
    def test_start(self, start_action_mock, filter_mock):

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'instance-view',
                 'key': 'statuses[].code',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': 'PowerState/running'}],
            'actions': [
                {'type': 'start'}
            ]
        })
        p.run()
        start_action_mock.assert_called_with(
            self.fake_running_vms[0]['resourceGroup'],
            self.fake_running_vms[0]['name'])

    @arm_template('vm.json')
    @patch('c7n_azure.resources.vm.InstanceViewFilter.process', return_value=fake_running_vms)
    @patch('c7n_azure.resources.vm.VmRestartAction.restart')
    def test_restart(self, restart_action_mock, filter_mock):

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'instance-view',
                 'key': 'statuses[].code',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': 'PowerState/running'}],
            'actions': [
                {'type': 'restart'}
            ]
        })
        p.run()
        restart_action_mock.assert_called_with(
            self.fake_running_vms[0]['resourceGroup'],
            self.fake_running_vms[0]['name'])

    @arm_template('vm.json')
    @patch('c7n_azure.resources.vm.InstanceViewFilter.process', return_value=fake_running_vms)
    @patch('c7n_azure.actions.DeleteAction.process', return_value='')
    def test_delete(self, delete_action_mock, filter_mock):

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'instance-view',
                 'key': 'statuses[].code',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': 'PowerState/running'}],
            'actions': [
                {'type': 'delete'}
            ]
        })
        p.run()
        delete_action_mock.assert_called_with(self.fake_running_vms)

    @arm_template('vm.json')
    def test_find_vm_with_public_ip(self):

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'network-interface',
                 'key': 'properties.ipConfigurations[].properties.publicIPAddress.id',
                 'op': 'eq',
                 'value': 'not-null'}
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-azure-vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'network-interface',
                 'key': 'properties.ipConfigurations[].properties.publicIPAddress.id',
                 'op': 'eq',
                 'value': 'null'}
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)
