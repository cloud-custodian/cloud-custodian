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


class ShortTermBackupRetentionPolicyFilterTest(BaseTest):

    def test_validate_short_term_backup_retention_policy_filter_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'short-term-schema-validate',
                'resource': 'azure.sqldatabase',
                'filters': [
                    {
                        'type': 'short-term-backup-retention-policy',
                        'op': 'gte',
                        'retention-period-days': 60
                    }
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_find_database_with_short_term_retention_at_14_days(self):
        p = self.load_policy({
            'name': 'find-database-with-short-term-retention-at-14-days',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cctestdb'
                },
                {
                    'type': 'short-term-backup-retention-policy',
                    'retention-period-days': 14
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_filter_database_with_short_term_retention_at_14_days(self):
        p = self.load_policy({
            'name': 'find-database-with-short-term-retention-at-14-days',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cctestdb'
                },
                {
                    'type': 'short-term-backup-retention-policy',
                    'op': 'ne',
                    'retention-period-days': 14
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)


class LongTermBackupRetentionPolicyFilterTest(BaseTest):

    def test_validate_long_term_backup_retention_policy_filter_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'long-term-schema-validate',
                'resource': 'azure.sqldatabase',
                'filters': [
                    {
                        'type': 'long-term-backup-retention-policy',
                        'backup-type': 'weekly',
                        'op': 'gt',
                        'retention-period': 1,
                        'retention-period-units': 'year'
                    }
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_find_database_with_weekly_backup_retention_less_than_2_months(self):

        p = self.load_policy({
            'name': 'find-db-with-weekly-backup-retention-less-than-2-months',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cclongtermretentiondb',
                },
                {
                    'type': 'long-term-backup-retention-policy',
                    'backup-type': 'weekly',
                    'op': 'lt',
                    'retention-period': 2,
                    'retention-period-units': 'months',
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_filter_database_with_yearly_backup_retention_more_than_18_months(self):

        p = self.load_policy({
            'name': 'filter-db-with-yearly-backup-retention-more-than-18-months',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cctestdb'
                },
                {
                    'type': 'long-term-backup-retention-policy',
                    'backup-type': 'yearly',
                    'op': 'lte',
                    'retention-period': 18,
                    'retention-period-units': 'months'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_find_database_with_long_term_policy_using_filter_or_operator(self):

        p = self.load_policy({
            'name': 'test-find-database-with-long-term-policy-using-filter-or-operator',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cclongtermretentiondb'
                },
                {
                    'or': [
                        {
                            'type': 'long-term-backup-retention-policy',
                            'backup-type': 'monthly',
                            'op': 'gte',
                            'retention-period': 12,
                            'retention-period-units': 'months'
                        },
                        {
                            'type': 'long-term-backup-retention-policy',
                            'backup-type': 'monthly',
                            'op': 'gte',
                            'retention-period': 1,
                            'retention-period-units': 'year'
                        },
                    ]
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_filter_database_with_retention_period_unit_mismatch(self):

        p = self.load_policy({
            'name': 'test-filter-database-with-retention-period-unit-mismatch',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cctestdb'
                },
                {
                    'type': 'long-term-backup-retention-policy',
                    'backup-type': 'weekly',
                    'op': 'eq',
                    'retention-period': 2,
                    'retention-period-units': 'weeks'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 0)
