# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class AksTest(BaseTest):
    def setUp(self):
        super(AksTest, self).setUp()

    def test_aks_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-aks',
                'resource': 'azure.aks'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cdnprofile.json')
    def test_find_aks_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-aks',
            'resource': 'azure.aks',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestaks'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
