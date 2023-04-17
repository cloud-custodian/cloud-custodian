# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class MariaDBTest(BaseTest):
    def test_azure_mariadb_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-mariadb',
                'resource': 'azure.mariadb'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('mariadb.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-mariadb',
            'resource': 'azure.mariadb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'ccmariadb8c5acbfeb94e'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
