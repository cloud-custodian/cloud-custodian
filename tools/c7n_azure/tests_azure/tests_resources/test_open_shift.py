# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class OpenShift(BaseTest):
    def setUp(self):
        super(OpenShift, self).setUp()

    def test_open_shift_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-open-shift',
                'resource': 'azure.open-shift'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cdnprofile.json')
    def test_find_open_shift_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-open-shift',
            'resource': 'azure.open-shift',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'environment-64ozd'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
