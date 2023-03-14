# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from ..azure_common import BaseTest, arm_template


class PostgresqlDatabaseTest(BaseTest):

    def test_postgresql_database_schema_validate(self):
        p = self.load_policy({
            'name': 'test-postgresql-database-schema-validate',
            'resource': 'azure.postgresql-database'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('postgresql.json')
    # Due to the COVID-19 Azure hardened quota limits for internal subscriptions and
    # postgresql can't be provisioned.
    @pytest.mark.skiplive
    def test_find_database_by_name(self):
        p = self.load_policy({
            'name': 'test-get-database-by-name',
            'resource': 'azure.postgresql-database',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cctestdb'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
