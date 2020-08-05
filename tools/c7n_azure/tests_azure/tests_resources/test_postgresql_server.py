# Copyright 2019 Microsoft Corporation
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from ..azure_common import BaseTest, arm_template


class PostgresqlServerTest(BaseTest):

    def test_postgresql_server_schema_validate(self):
        p = self.load_policy({
            'name': 'test-postgresql-server-schema-validate',
            'resource': 'azure.postgresql-server'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('postgresql.json')
    # Due to the COVID-19 Azure hardened quota limits for internal subscriptions and
    # postgresql can't be provisioned.
    @pytest.mark.skiplive
    def test_find_server_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-postgresql-server',
            'resource': 'azure.postgresql-server',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestpostgresqlserver*'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
