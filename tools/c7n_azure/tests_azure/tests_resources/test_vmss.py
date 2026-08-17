# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from azure.mgmt.compute.models import Sku, VirtualMachineScaleSetUpdate

from ..azure_common import BaseTest, arm_template, cassette_name

_VMSS_BEGIN_UPDATE = (
    'azure.mgmt.compute.v2024_11_01.operations'
    '._operations.VirtualMachineScaleSetsOperations.begin_update'
)


class VMSSTest(BaseTest):
    def setUp(self):
        super(VMSSTest, self).setUp()

    def test_validate_vmss_schemas(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-azure-vmss',
                'resource': 'azure.vmss'
            }, validate=True)

            self.assertTrue(p)

    def test_validate_scale_schema(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-vmss-scale',
                'resource': 'azure.vmss',
                'actions': [{'type': 'scale', 'capacity': 2}]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('vmss.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-vm-scale-set',
            'resource': 'azure.vmss',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctestvmss'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @patch(_VMSS_BEGIN_UPDATE)
    @arm_template('vmss.json')
    @cassette_name('test_find_by_name')
    def test_scale_action(self, scale_mock):
        p = self.load_policy({
            'name': 'test-vmss-scale',
            'resource': 'azure.vmss',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctestvmss'}],
            'actions': [{'type': 'scale', 'capacity': 1}]
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(1, scale_mock.call_count)
        scale_mock.assert_called_with(
            resources[0]['resourceGroup'],
            resources[0]['name'],
            VirtualMachineScaleSetUpdate(
                sku=Sku(
                    name=resources[0]['sku']['name'],
                    tier=resources[0]['sku']['tier'],
                    capacity=1
                )
            )
        )
