# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class MySQLTest(BaseTest):
    def test_azure_mysql_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-mysql',
            'resource': 'azure.mysql'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-mysql',
            'resource': 'azure.mysql',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccmysql*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
