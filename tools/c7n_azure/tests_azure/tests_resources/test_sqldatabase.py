# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from azure.mgmt.sql.models import DatabaseUpdate, Sku, BackupShortTermRetentionPolicy
from ..azure_common import BaseTest, arm_template, cassette_name, requires_arm_polling
from c7n_azure.resources.sqldatabase import (
    BackupRetentionPolicyHelper, ShortTermBackupRetentionPolicyAction)
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser
from mock import patch

from c7n.exceptions import PolicyValidationError
from c7n.utils import local_session


class SqlDatabaseTest(BaseTest):

    def setUp(self):
        super(SqlDatabaseTest, self).setUp()
        self.client = local_session(Session).client('azure.mgmt.sql.SqlManagementClient')

    def test_sql_database_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-sql-database-schema-validate',
                'resource': 'azure.sql-database'
            }, validate=True)
            self.assertTrue(p)

            # test alias for back-compatibility
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
                },
                {
                    'type': 'value',
                    'key': 'sku.tier',
                    'op': 'eq',
                    'value': 'Standard'
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

    @arm_template('sqlserver.json')
    @patch('azure.mgmt.sql.operations.DatabasesOperations.begin_update')
    def test_resize_action(self, update_mock):
        p = self.load_policy({
            'name': 'resize-sqldatabase',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestdb'
                }
            ],
            'actions': [
                {
                    'type': 'resize',
                    'tier': 'Standard',
                    'capacity': 100,
                    'max_size_bytes': 21474836480
                }
            ],
        })

        self.resources = p.run()
        self.assertEqual(len(self.resources), 1)
        self.assertEqual(self.resources[0]['name'], 'cctestdb')

        parent_id = ResourceIdParser.get_resource_name(self.resources[0]['c7n:parent-id'])
        expected_db_update = DatabaseUpdate(sku=Sku(capacity=100, tier='Standard', name='Standard'),
                                            max_size_bytes=21474836480)

        update_mock.assert_called_once()
        _, args, _ = update_mock.mock_calls[0]
        self.assertEqual('test_sqlserver', args[0])
        self.assertEqual(parent_id, args[1])
        self.assertEqual('cctestdb', args[2])
        self.assertEqual(expected_db_update, args[3])

    def test_data_encryption_filter(self):
        p = self.load_policy({
            'name': 'test-azure-sql-database',
            'resource': 'azure.sql-database',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestdb'
                },
                {
                    'type': 'transparent-data-encryption',
                    'enabled': True
                }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))

    def test_data_masking_filter(self):
        p = self.load_policy({
            'name': 'test-azure-sql-database',
            'resource': 'azure.sql-database',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestdb'
                },
                {
                    'type': 'data-masking-policy',
                    'enabled': False
                }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))


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


class ShortTermBackupRetentionPolicyActionSchemaTest(BaseTest):

    def test_schema_with_valid_short_term_retention_period_values(self):
        for period in ShortTermBackupRetentionPolicyAction.VALID_RETENTION_PERIOD_DAYS:
            self._test_retention_period_days(days=period, valid=True)

    def test_schema_with_invalid_short_term_retention_period_values(self):
        for period in [5, 10, 20, 100]:
            self._test_retention_period_days(days=period, valid=False)

    def _test_retention_period_days(self, days, valid=True):

        def do_validation():
            with self.sign_out_patch():
                p = self.load_policy({
                    'name': 'short-term-action-schema-validate',
                    'resource': 'azure.sqldatabase',
                    'actions': [
                        {
                            'type': 'update-short-term-backup-retention-policy',
                            'retention-period-days': days
                        }
                    ]
                }, validate=True)
                return p

        if valid:
            p = do_validation()
            self.assertTrue(p, "Expected {} to be a valid retention period".format(days))
        else:
            with self.assertRaises(PolicyValidationError,
                    msg="Expected {} to be an invalid retention period".format(days)):
                do_validation()


# NOTE: Normally, updating the retention policy on a DB requires ARM polling to know when the
# operation has finished. However, this polling happens client-side and causes the tests to complete
# slowly. In order to speed these up, the cassettes were manually modified to immediately return the
# completed operation.
@requires_arm_polling
class ShortTermBackupRetentionPolicyActionTest(BaseTest):

    @classmethod
    def setUpClass(cls, *args, **kwargs):
        super(ShortTermBackupRetentionPolicyActionTest, cls).setUpClass(*args, **kwargs)
        cls.client = local_session(Session).client('azure.mgmt.sql.SqlManagementClient') \
            .backup_short_term_retention_policies

    def tearDown(self, *args, **kwargs):
        super(ShortTermBackupRetentionPolicyActionTest, self).tearDown(*args, **kwargs)
        args = list(self.retention_policy_context)
        args.append(BackupShortTermRetentionPolicy(retention_days=14))
        reverted_policy = ShortTermBackupRetentionPolicyActionTest.client.begin_create_or_update(
            *args).result()
        self.assertEqual(reverted_policy.retention_days, 14)

    @arm_template('sqlserver.json')
    def test_update_short_term_backup_retention_policy(self):
        p = self.load_policy({
            'name': 'test-update-short-term-backup-retention-policy',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cctestdb'
                },
            ],
            'actions': [
                {
                    'type': 'update-short-term-backup-retention-policy',
                    'retention-period-days': 28
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.retention_policy_context = \
            BackupRetentionPolicyHelper.get_backup_retention_policy_context(resources[0])
        self._assert_retention_period_equal(28)

    def _assert_retention_period_equal(self, days):
        current_retention_period = ShortTermBackupRetentionPolicyActionTest.client.get(
            *self.retention_policy_context
        )
        self.assertEqual(current_retention_period.retention_days, days)


class LongTermBackupRetentionPolicyActionSchemaTest(BaseTest):

    def test_schema_for_long_term_backup_retention_policy_action(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'long-term-action-schema-validate',
                'resource': 'azure.sqldatabase',
                'actions': [
                    {
                        'type': 'update-long-term-backup-retention-policy',
                        'backup-type': 'weekly',
                        'retention-period': 2,
                        'retention-period-units': 'weeks'
                    }
                ]
            }, validate=True)
            self.assertTrue(p)


# NOTE: Normally, updating the retention policy on a DB requires ARM polling to know when the
# operation has finished. However, this polling happens client-side and causes the tests to complete
# slowly. In order to speed these up, the cassettes were manually modified to immediately return the
# completed operation.
@requires_arm_polling
class LongTermBackupRetentionPolicyActionTest(BaseTest):

    @classmethod
    def setUpClass(cls, *args, **kwargs):
        super(LongTermBackupRetentionPolicyActionTest, cls).setUpClass(*args, **kwargs)
        cls.client = local_session(Session).client('azure.mgmt.sql.SqlManagementClient') \
            .backup_long_term_retention_policies

    def tearDown(self, *args, **kwargs):
        default_long_term_policy = {
            'weekly_retention': 'P1M',
            'monthly_retention': 'P12M',
            'yearly_retention': None
        }

        super(LongTermBackupRetentionPolicyActionTest, self).tearDown(*args, **kwargs)

        params = list(self.retention_policy_context)
        params.append(default_long_term_policy)
        reverted_policy = LongTermBackupRetentionPolicyActionTest.client.begin_create_or_update(
            *params).result()

        self.assertEqual(reverted_policy.weekly_retention, 'P1M')
        self.assertEqual(reverted_policy.monthly_retention, 'P12M')
        self.assertEqual(reverted_policy.yearly_retention, 'PT0S')

    @arm_template('sqlserver.json')
    def test_update_weekly_retention_policy(self):

        p = self.load_policy({
            'name': 'test-update-weekly-retention-policy',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cclongtermretentiondb'
                },
            ],
            'actions': [
                {
                    'type': 'update-long-term-backup-retention-policy',
                    'backup-type': 'weekly',
                    'retention-period': 10,
                    'retention-period-units': 'days',
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.retention_policy_context = \
            BackupRetentionPolicyHelper.get_backup_retention_policy_context(resources[0])
        self._assert_retention_period_equal(
            BackupRetentionPolicyHelper.LongTermBackupType.weekly.retention_property,
            'P10D'
        )

    @arm_template('sqlserver.json')
    def test_update_monthly_retention_policy(self):
        p = self.load_policy({
            'name': 'test-update-monthly-retention-policy',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cclongtermretentiondb'
                },
            ],
            'actions': [
                {
                    'type': 'update-long-term-backup-retention-policy',
                    'backup-type': 'monthly',
                    'retention-period': 6,
                    'retention-period-units': 'weeks',
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.retention_policy_context = \
            BackupRetentionPolicyHelper.get_backup_retention_policy_context(resources[0])
        self._assert_retention_period_equal(
            BackupRetentionPolicyHelper.LongTermBackupType.monthly.retention_property,
            'P6W'
        )

    @arm_template('sqlserver.json')
    def test_update_yearly_retention_policy(self):
        p = self.load_policy({
            'name': 'test-update-yearly-retention-policy',
            'resource': 'azure.sqldatabase',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cclongtermretentiondb'
                },
            ],
            'actions': [
                {
                    'type': 'update-long-term-backup-retention-policy',
                    'backup-type': 'yearly',
                    'retention-period': 2,
                    'retention-period-units': 'years',
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.retention_policy_context = \
            BackupRetentionPolicyHelper.get_backup_retention_policy_context(resources[0])
        self._assert_retention_period_equal(
            BackupRetentionPolicyHelper.LongTermBackupType.yearly.retention_property,
            'P2Y'
        )

    def _assert_retention_period_equal(self, retention_property, period):
        current_retention_period = LongTermBackupRetentionPolicyActionTest.client.get(
            *self.retention_policy_context
        )
        self.assertEqual(getattr(current_retention_period, retention_property), period)


class SqlDatabaseDataEncryptionFilterTest(BaseTest):

    @cassette_name('data_encryption_filter')
    @arm_template('sqlserver.json')
    def test_filter(self):
        p = self.load_policy({
            'name': 'test-azure-sql-data-encryption',
            'resource': 'azure.sql-database',
            'filters': [
                {'type': 'data-encryption',
                 'enabled': False}],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('9958f24e-907d-4b98-8b89-a8ac1d748225',
                         resources[0]['properties']['databaseId'])
