# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class MariaDBTest(BaseTest):
    def test_azure_mariadb_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-mariadb',
            'resource': 'azure.mariadb'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-mariadb',
            'resource': 'azure.mariadb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccmariadb*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
