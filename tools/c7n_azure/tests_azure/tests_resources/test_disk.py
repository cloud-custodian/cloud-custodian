# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import local_session
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser
import pytest
from ..azure_common import BaseTest, arm_template, cassette_name


class DiskTest(BaseTest):
    def setUp(self):
        super(DiskTest, self).setUp()

    def test_azure_disk_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-disk',
                'resource': 'azure.disk'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('disk.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-disk',
            'resource': 'azure.disk',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctestvm_OsDisk_1_81338ced63fa4855b8a5f3e2bab5213c'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class ModifyDiskTypeTests(BaseTest):
    """Test class for modifying disk types (SKU) of Azure disks."""

    def setUp(self, *args, **kwargs):
        super(ModifyDiskTypeTests, self).setUp(*args, **kwargs)
        self.client = local_session(Session).client('azure.mgmt.compute.ComputeManagementClient')

    def tearDown(self, *args, **kwargs):
        super(ModifyDiskTypeTests, self).tearDown(*args, **kwargs)

    def _fetch_disk(self, disk_id):
        """
        Fetch disk details using Azure SDK.
        :param disk_id: The full resource ID of the disk.
        :return: Disk resource object.
        """
        resource_group, disk_name = self._extract_resource_group_and_name(disk_id)
        return self.client.disks.get(resource_group, disk_name)

    def _extract_resource_group_and_name(self, resource_id):
        """
        Extracts the resource group and resource name from a given Azure resource ID.
        Uses the standardized ResourceIdParser for consistency across the project.
        """
        resource_group = ResourceIdParser.get_resource_group(resource_id)
        resource_name = ResourceIdParser.get_resource_name(resource_id)
        return resource_group, resource_name

    @pytest.mark.vcr(record_mode='ALL')
    @arm_template('disk_type_modify.json')
    @cassette_name('change_sku_unattached_disks')
    def test_change_sku_unattached_disks(self):
        """Test to validate unattached disk SKU change"""
        policy = self.load_policy(
            {
                'name': 'change-unattached-disk-type',
                'resource': 'azure.disk',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'properties.diskState',
                        'op': 'eq',
                        'value': 'Unattached',
                    },
                    {
                        'type': 'value',
                        'key': "id",
                        'op': 'regex',
                        'value': ".*/resourceGroups/TEST_DISK_TYPE_MODIFY/.*",
                    },
                ],
                'actions': [{'type': 'modify-disk-type', 'new_sku': 'Standard_LRS'}],
            }
        , validate=True)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        # Validate using Azure SDK
        for resource in resources:
            disk = self._fetch_disk(resource['id'])
            self.assertEqual(disk.sku.name, 'Standard_LRS')

    @pytest.mark.vcr(record_mode='ALL')
    @arm_template('disk_type_modify.json')
    @cassette_name('change-attached-disk-type')
    def test_change_sku_attached_disks(self):
        """Test to validate attached disk SKU change"""
        policy = self.load_policy(
            {
                'name': 'change-attached-disk-type',
                'resource': 'azure.disk',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'properties.diskState',
                        'op': 'eq',
                        'value': 'Attached',
                    },
                    {
                        'type': 'value',
                        'key': 'id',
                        'op': 'regex',
                        'value': ".*/resourceGroups/TEST_DISK_TYPE_MODIFY/.*",
                    }
                ],
                'actions': [{'type': 'modify-disk-type', 'new_sku': 'Standard_LRS'}],
            }
        , validate=True)

        resources = policy.run()
        self.assertEqual(len(resources), 2)

        # Validate using Azure SDK
        for resource in resources:
            disk = self._fetch_disk(resource['id'])
            self.assertEqual(disk.sku.name, 'Standard_LRS')

    @pytest.mark.vcr(record_mode='ALL')
    @arm_template('disk_type_modify.json')
    @cassette_name('no-change-for-correct-type')
    def test_no_change_for_correct_sku(self):
        """Test to validate no change for disks with correct SKU"""
        policy = self.load_policy(
            {
                'name': 'no-change-for-correct-type',
                'resource': 'azure.disk',
                'filters': [
                    {'type': 'value', 'key': 'sku.name', 'op': 'eq', 'value': 'Standard_LRS'},
                    {
                        'type': 'value',
                        'key': 'id',
                        'op': 'regex',
                        'value': ".*/resourceGroups/TEST_DISK_TYPE_MODIFY/.*",
                    },
                ],
                'actions': [{'type': 'modify-disk-type', 'new_sku': 'Standard_LRS'}],
            }
        , validate=True)

        resources = policy.run()
        self.assertEqual(len(resources), 3)

        # Validate using Azure SDK
        for resource in resources:
            disk = self._fetch_disk(resource['id'])
            self.assertEqual(disk.sku.name, 'Standard_LRS')

    @pytest.mark.vcr(record_mode='ALL')
    @arm_template('disk_type_modify.json')
    @cassette_name('skip-unsupported-disk-state')
    def test_skip_unsupported_disk_state(self):
        """Test to validate skipping of unsupported disk states"""
        policy = self.load_policy(
            {
                'name': 'skip-unsupported-disk-state',
                'resource': 'azure.disk',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'sku.name',
                        'op': 'eq',
                        'value': 'ActiveSAS',
                    },
                    {
                        'type': 'value',
                        'key': 'id',
                        'op': 'regex',
                        'value': ".*/resourceGroups/TEST_DISK_TYPE_MODIFY/.*",
                    },
                ],
                'actions': [{'type': 'modify-disk-type', 'new_sku': 'Standard_LRS'}],
            }
        , validate=True)

        resources = policy.run()
        self.assertEqual(len(resources), 0)
