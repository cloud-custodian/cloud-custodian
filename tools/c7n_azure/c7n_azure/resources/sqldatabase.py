# Copyright 2018 Capital One Services, LLC
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
# limitations under the License.from c7n_azure.provider import resources

import enum
import isodate
from datetime import datetime, timedelta
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager
from c7n_azure.query import ChildResourceQuery
from c7n_azure.filters import scalar_ops
from c7n.filters import Filter
from c7n.utils import type_schema
from msrestazure.azure_exceptions import CloudError
from msrestazure.tools import parse_resource_id


@resources.register('sqldatabase')
class SqlDatabase(ChildArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('databases', 'list_by_server', {
            'resource_group_name': 'resourceGroup',
            'server_name': 'name'
        })
        parent_spec = ChildArmResourceManager.ParentSpec(
            manager_name='sqlserver',
            annotate_parent=True
        )


class BackupRetentionPolicyFilter(Filter):

    schema = type_schema(
        'backup-retention-policy',
        **{
            'op': {'enum': list(scalar_ops.keys())},
        },
    )

    def __init__(self, operations_property, data, manager=None):
        super(BackupRetentionPolicyFilter, self).__init__(data, manager)
        self.operations_property = operations_property

    def list_backup_retention_policies(self, i):
        client = self.manager.get_client()
        list_operation = getattr(client, self.operations_property).list_by_database

        resource_group_name = i.get('resourceGroup')
        server_name = BackupRetentionPolicyFilter.get_sql_server_name(
            i.get(ChildResourceQuery.parent_key))
        database_name = i.get('name')

        list_response = list_operation(
            resource_group_name, server_name, database_name)
        return list_response

    def __call__(self, i):
        retention_policies = self.list_backup_retention_policies(i)
        return self.filter_with_retention_policies(i, retention_policies)

    def filter_with_retention_policies(self, i, retention_policies):
        raise NotImplementedError()

    def perform_op(self, a, b):
        op = scalar_ops.get(self.data.get('op', 'eq'))
        return op(a, b)

    @staticmethod
    def get_sql_server_name(sql_server_id):
        parsed = parse_resource_id(sql_server_id)
        return parsed.get('name')


@SqlDatabase.filter_registry.register('short-term-backup-retention-policy')
class ShortTermBackupRetentionPolicyFilter(BackupRetentionPolicyFilter):
    """

    Filter SQL Databases on the length of their short term backup retention policies.

    If the database has no backup retention policies, the database is treated as if
    it has a backup retention of zero days.

    :example: Find all SQL Databases with a short term retention policy shorter than 2 weeks.

    .. code-block:: yaml

            policies:
              - name: short-term-backup-retention-policy
                resource: azure.sqldatabase
                filters:
                  - type: short-term-backup-retention-policy
                    op: lt
                    retention-period-days: 14

    """

    schema = type_schema(
        'short-term-backup-retention-policy',
        required=['retention-period-days'],
        rinherit=BackupRetentionPolicyFilter.schema,
        **{
            'retention-period-days': {'type': 'number'},
        },
    )

    def __init__(self, data, manager=None):
        super(ShortTermBackupRetentionPolicyFilter, self).__init__(
            'backup_short_term_retention_policies', data, manager)
        self.retention_period_days_limit = self.data.get('retention-period-days')

    def filter_with_retention_policies(self, i, retention_policies):
        try:
            # TODO: re-think this to better handle the case of multiple backup policies...
            # (can there be mutliple backup policies?)
            for retention_policy in retention_policies:
                actual_retention_days = retention_policy.retention_days
                return self.perform_op(actual_retention_days, self.retention_period_days_limit)
        except CloudError as e:
            # TODO: is there a way to figure this out before trying to iterate through
            # backup policies?
            if e.status_code == 404:
                return self.filter_without_retention_policies(i)
            else:
                raise e

    def filter_without_retention_policies(self, i):
        # without any backup retention policies, this is effectively 0 days of retention
        return self.perform_op(0, self.retention_period_days_limit)


@SqlDatabase.filter_registry.register('long-term-backup-retention-policy')
class LongTermBackupRetentionPolicyFilter(BackupRetentionPolicyFilter):
    """

    Filter SQL Databases on the length of their long term backup retention policies.

    There are 3 backup types for a sql database: weekly, monthly, and yearly. And, each
    of these backups has a retention period that can specified in units of days, weeks,
    months, or years.

    :example: Find all SQL Databases with weekly backup retentions longer than 1 month.

    .. code-block:: yaml

            policies:
              - name: long-term-backup-retention-policy
                resource: azure.sqldatabase
                filters:
                  - type: long-term-backup-retention-policy
                    backup-type: weekly
                    op: gt
                    retention-period: 1
                    retention-period-units: months

    """

    @enum.unique
    class BackupType(enum.Enum):
        weekly = 'weekly'
        monthly = 'monthly'
        yearly = 'yearly'

        def __str__(self):
            return self.value

    @enum.unique
    class RetentionPeriodUnits(enum.Enum):
        day = ('day', 'D')
        days = ('days', 'D')
        week = ('week', 'W')
        weeks = ('weeks', 'W')
        month = ('month', 'M')
        months = ('months', 'M')
        year = ('year', 'Y')
        years = ('years', 'Y')

        def __init__(self, str_value, iso8601_symbol):
            self.str_value = str_value
            self.iso8601_symbol = iso8601_symbol

        def __str__(self):
            return self.str_value

    schema = type_schema(
        'long-term-backup-retention-policy',
        required=['backup-type', 'retention-period', 'retention-period-units'],
        rinherit=BackupRetentionPolicyFilter.schema,
        **{
            'backup-type': {'enum': list([str(t) for t in BackupType])},
            'retention-period': {'type': 'number'},
            'retention-period-units': {'enum': list([str(u) for u in RetentionPeriodUnits])},
        },
    )

    def __init__(self, data, manager=None):
        super(LongTermBackupRetentionPolicyFilter, self).__init__(
            'backup_long_term_retention_policies', data, manager)
        self.backup_type = self.data.get('backup-type')

        retention_period = self.data.get('retention-period')
        retention_period_units = LongTermBackupRetentionPolicyFilter.RetentionPeriodUnits[
            self.data.get('retention-period-units')]
        self.duration_limit = LongTermBackupRetentionPolicyFilter.period_to_duration_limit(
            retention_period, retention_period_units)

    @staticmethod
    def period_to_duration_limit(period, unit):
        iso8601_str = "P{}{}".format(period, unit.iso8601_symbol)
        duration = isodate.parse_duration(iso8601_str)
        return LongTermBackupRetentionPolicyFilter.normalize_duration(duration)

    @staticmethod
    def normalize_duration(duration):
        if isinstance(duration, isodate.Duration):
            now = datetime.now()
            duration = duration.totimedelta(start=now)
        if not isinstance(duration, timedelta):
            raise ValueError("Could not normalize {} to a timedelta".format(duration))
        return duration

    def filter_with_retention_policies(self, i, retention_policies):

        if self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.weekly.value:
            actual_retention_days_iso8601 = retention_policies.weekly_retention
        elif self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.monthly.value:
            actual_retention_days_iso8601 = retention_policies.monthly_retention
        elif self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.yearly.value:
            actual_retention_days_iso8601 = retention_policies.yearly_retention
        else:
            raise ValueError("Unknown backup-type: {}".format(self.backup_type))

        # TODO figure out a better way to compare durations
        # https://docs.microsoft.com/en-us/azure/sql-database/sql-database-long-term-retention
        #
        # given ISO 8601 duration: P30D and P1M:
        #   in february : P30D > P1M
        #   in april    : P30D = P1M
        #   in may      : P30D < P1M

        actual_duration = isodate.parse_duration(actual_retention_days_iso8601)
        actual_duration = LongTermBackupRetentionPolicyFilter.normalize_duration(actual_duration)
        result = self.perform_op(actual_duration, self.duration_limit)
        return result
