# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime

from azure.mgmt.compute.models import HardwareProfile, VirtualMachineUpdate
from ..azure_common import BaseTest, arm_template
from c7n_azure.session import Session
from dateutil import tz as tzutils
from mock import patch

from c7n.testing import mock_datetime_now
from c7n.utils import local_session


class VMTest(BaseTest):
    def setUp(self):
        super(VMTest, self).setUp()

    def test_validate_vm_schemas(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-azure-vm',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'offhour'},
                    {'type': 'onhour'},
                    {'type': 'network-interface'},
                    {'type': 'instance-view'}
                ],
                'actions': [
                    {'type': 'poweroff'},
                    {'type': 'stop'},
                    {'type': 'start'},
                    {'type': 'resize', 'vmSize': 'Standard_A1_v2'},
                    {'type': 'restart'},
                    {'type': 'poweroff'}
                ]
            }, validate=True)

            self.assertTrue(p)

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
        'resourceGroup': 'TEST_VM',
        'name': 'cctestvm'
    }]

    @arm_template('vm.json')
    @patch('c7n_azure.resources.vm.InstanceViewFilter.process', return_value=fake_running_vms)
    def test_stop(self, filter_mock):
        with patch(self._get_vm_client_string() + '.deallocate') as stop_action_mock:
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
    def test_poweroff(self, filter_mock):
        with patch(self._get_vm_client_string() + '.power_off') as poweroff_action_mock:
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
                self.fake_running_vms[0]['name'],
            )

    @arm_template('vm.json')
    @patch('c7n_azure.resources.vm.InstanceViewFilter.process', return_value=fake_running_vms)
    def test_start(self, filter_mock):
        with patch(self._get_vm_client_string() + '.start') as start_action_mock:

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
    def test_restart(self, filter_mock):
        with patch(self._get_vm_client_string() + '.restart') as restart_action_mock:
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
    def test_resize(self, resize_action_mock):
        with patch(self._get_vm_client_string() + '.update') as resize_action_mock:
            p = self.load_policy({
                'name': 'test-azure-vm',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value_type': 'normalize',
                     'value': 'cctestvm'}],
                'actions': [
                    {'type': 'resize',
                     'vmSize': 'Standard_A2_v2'}
                ]
            })
            p.run()

        expected_hardware_profile = HardwareProfile(vm_size='Standard_A2_v2')

        resize_action_mock.assert_called_with(
            self.fake_running_vms[0]['resourceGroup'],
            self.fake_running_vms[0]['name'],
            VirtualMachineUpdate(hardware_profile=expected_hardware_profile)
        )

    @arm_template('vm.json')
    @patch('c7n_azure.resources.vm.InstanceViewFilter.process', return_value=fake_running_vms)
    @patch('c7n_azure.actions.delete.DeleteAction.process', return_value='')
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

    @arm_template('vm.json')
    def test_on_off_hours(self):

        t = datetime.datetime.now(tzutils.gettz("pt"))
        t = t.replace(year=2018, month=8, day=24, hour=18, minute=30)

        with mock_datetime_now(t, datetime):
            p = self.load_policy({
                'name': 'test-azure-vm',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'offhour',
                     'default_tz': "pt",
                     'offhour': 18,
                     'tag': 'schedule'}
                ],
            })

            resources = p.run()
            self.assertEqual(len(resources), 1)

        t = t.replace(year=2018, month=8, day=24, hour=8, minute=30)

        with mock_datetime_now(t, datetime):
            p = self.load_policy({
                'name': 'test-azure-vm',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'onhour',
                     'default_tz': "pt",
                     'onhour': 8,
                     'tag': 'schedule'}
                ],
            })

            resources = p.run()
            self.assertEqual(len(resources), 1)

    def _get_vm_client_string(self):
        client = local_session(Session)\
            .client('azure.mgmt.compute.ComputeManagementClient').virtual_machines
        return client.__module__ + '.' + client.__class__.__name__
