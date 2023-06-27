# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class VNetTest(BaseTest):
    def setUp(self):
        super(VNetTest, self).setUp()

    def test_validate_vnet_schemas(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-azure-vnet',
                'resource': 'azure.vnet'
            }, validate=True)

            self.assertTrue(p)
