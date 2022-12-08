# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


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
