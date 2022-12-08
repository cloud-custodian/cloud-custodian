# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class DataLakeTest(BaseTest):
    def setUp(self):
        super(DataLakeTest, self).setUp()

    def test_data_lake_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-data-lake',
                'resource': 'azure.datalake'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('datalake.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-datalake',
            'resource': 'azure.datalake',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccdatalake*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
