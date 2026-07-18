# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest


class PostgreSQLFlexibleServerTest(BaseTest):
    def test_mysql_flexibleserver_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-postgresql-flexibleserver',
            'resource': 'azure.postgresql-flexibleserver'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-postgresql-flexibleserver',
            'resource': 'azure.postgresql-flexibleserver',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'pgtestsvc4'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
