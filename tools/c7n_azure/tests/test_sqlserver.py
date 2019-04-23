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

    TEST_DATE = datetime.datetime(2019, 4, 21, 14, 10, 00)

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
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'}],
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
