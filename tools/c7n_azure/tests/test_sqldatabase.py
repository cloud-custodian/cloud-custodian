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

from azure_common import BaseTest, arm_template


class SqlDatabaseTest(BaseTest):

    def test_sql_database_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-sql-database-schema-validate',
                'resource': 'azure.sqldatabase'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('sqlserver.json')
    def test_get_database_by_name(self):
        p = self.load_policy({
            'name': 'test-get-database-by-name',
            'resource': 'azure.sqldatabase',
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
        self._assert_found_only_test_database(resources)

    @arm_template('sqlserver.json')
    def test_find_databases_with_premium_sku(self):
        p = self.load_policy({
            'name': 'test-find-databases-with-premium-sku',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'sku.tier',
                    'op': 'eq',
                    'value': 'Premium'
                }
            ]
        })

        resources = p.run()
        self._assert_found_only_test_database(resources)

    @arm_template('sqlserver.json')
    def _assert_found_only_test_database(self, resources):
        self.assertEqual(len(resources), 1)
        db = resources[0]

        self.assertEqual(db.get('name'), 'cctestdb')
