# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest

import datetime
from mock import patch


class SqlServerTest(BaseTest):

    TEST_DATE = datetime.datetime(2019, 4, 18, 14, 10, 00)

    def test_sql_server_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-policy-assignment',
                'resource': 'azure.sqlserver'
            }, validate=True)
            self.assertTrue(p)

    # run ./templates/provision.sh sqlserver to deploy required resource.
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver12262018'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    def test_metric_elastic_exclude(self, utcnow):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'metric',
                 'metric': 'dtu_consumption_percent',
                 'op': 'lt',
                 'aggregation': 'average',
                 'threshold': 10,
                 'timeframe': 72,
                 'filter': "ElasticPoolResourceId eq '*'"
                 }],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    def test_metric_elastic_include(self, utcnow):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'metric',
                 'metric': 'dtu_consumption_percent',
                 'op': 'lt',
                 'aggregation': 'average',
                 'threshold': 10,
                 'timeframe': 72,
                 'filter': "ElasticPoolResourceId eq '*'",
                 'no_data_action': 'include'
                 }],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    def test_metric_database(self, utcnow):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'metric',
                 'metric': 'dtu_consumption_percent',
                 'op': 'lt',
                 'aggregation': 'average',
                 'threshold': 10,
                 'timeframe': 72,
                 'filter': "DatabaseResourceId eq '*'"
                 }],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_sql_database_view_filter_adds_database_view(self):

        p = self.load_policy({
            'name': 'test-sql-database-view-filter-adds-database-view',
            'resource': 'azure.sqlserver',
            'filters': [{'type': 'sql-database-view'}]
        })

        resources = p.run()
        sqlserver = self._assert_cctestsqlserver_was_found(resources)

        databases = sqlserver.get('databases')
        self.assertIsNotNone(databases, "The database view was not appended to the sqlserver model")
        self.assertEqual(2, len(databases), "There should be 2 databases on this sql server")

        for database in databases:
            self._assert_valid_database_model_format(database)

    def test_find_by_database_with_name(self):

        p = self.load_policy({
            'name': 'test-find-by-database-with-name',
            'resource': 'azure.sqlserver',
            'filters': [
                {
                    'type': 'sql-database-view'
                },
                {
                    'type': 'value',
                    'key': 'databases[?name==\'cctestdb\']',
                    'value': 'not-null'
                }
            ]
        })

        resources = p.run()
        self._assert_cctestsqlserver_was_found(resources)

    def test_find_by_database_with_premium_sku(self):

        p = self.load_policy({
            'name': 'test-find-by-database-with-premium-sku',
            'resource': 'azure.sqlserver',
            'filters': [
                {
                    'type': 'sql-database-view'
                },
                {
                    'type': 'value',
                    'key': 'databases[?sku.tier==\'Premium\']',
                    'value': 'not-null'
                }
            ]
        })

        resources = p.run()
        self._assert_cctestsqlserver_was_found(resources)

    def test_filtering_on_database_field_value(self):

        p = self.load_policy({
            'name': 'test-filtering-on-database-field-value',
            'resource': 'azure.sqlserver',
            'filters': [
                {
                    'type': 'sql-database-view'
                },
                {
                    'type': 'value',
                    'key': 'databases[?name==\'this-db-doesnt-exist\']',
                    'value': 'not-null'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(0, len(resources), "There shouldn't be any SqlServers here")

    def _assert_cctestsqlserver_was_found(self, resources):

        self.assertEqual(len(resources), 1, "Expected a single SqlServer")
        sqlserver = resources[0]
        self.assertEqual('cctestsqlserver12262018', sqlserver.get('name'),
                         "The wrong sqlserver was found")

        return sqlserver

    def _assert_valid_database_model_format(self, database):

        self.assertTrue(type(database) is dict, "The database is not a dictionary")

        # field check is not exhaustive, but enough to be confident that the full model is present
        string_fields = ['id', 'name', 'type', 'location', 'status', 'database_id']
        for string_field in string_fields:
            self.assertTrue(type(database.get(string_field) is str))

        sku = database.get('sku')
        self.assertTrue(type(sku) is dict)
        self.assertTrue(type(sku.get('tier') is str))
