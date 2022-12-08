# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


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
