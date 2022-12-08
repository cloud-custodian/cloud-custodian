# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class DataFactoryTest(BaseTest):
    def setUp(self):
        super(DataFactoryTest, self).setUp()

    def test_data_factory_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-data-factory',
                'resource': 'azure.datafactory'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('datafactory.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-data-factory',
            'resource': 'azure.datafactory',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cctest-data-factory*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
