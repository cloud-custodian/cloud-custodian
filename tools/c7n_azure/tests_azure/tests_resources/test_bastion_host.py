# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class BastionHostTest(BaseTest):
    def setUp(self):
        super(BastionHostTest, self).setUp()

    def test_bastion_host_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-bastion-host',
                'resource': 'azure.bastion-host'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('bastion-host.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-bastion-host',
            'resource': 'azure.bastion-host',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cctest*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
