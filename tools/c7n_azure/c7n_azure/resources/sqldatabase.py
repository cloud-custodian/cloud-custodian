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
import operator
from datetime import datetime, timedelta
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager
from c7n_azure.query import ChildResourceQuery
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

    # TODO: consolidate with MetricFilter.op?
    number_ops = {
        'eq': operator.eq,
        'equal': operator.eq,
        'ne': operator.ne,
        'not-equal': operator.ne,
        'gt': operator.gt,
        'greater-than': operator.gt,
        'ge': operator.ge,
        'gte': operator.ge,
        'le': operator.le,
        'lte': operator.le,
        'lt': operator.lt,
        'less-than': operator.lt
    }

    def __init__(self, operations_property, data, manager=None):
        super(BackupRetentionPolicyFilter, self).__init__(data, manager)
        self.operations_property = operations_property

    def list_backup_retention_policies(self, i):
        client = self.manager.get_client()
        list_operation = getattr(client, self.operations_property).list_by_database

        resource_group_name = i.get('resourceGroup')
        server_name = BackupRetentionPolicyFilter.get_sql_server_name(
            i[ChildResourceQuery.parent_key])
        database_name = i.get('name')

        list_response = list_operation(
            resource_group_name, server_name, database_name)
        return list_response

    def __call__(self, i):
        policies = self.list_backup_retention_policies(i)
        return self.filter_with_policies(i, policies)

    def filter_with_policies(self, i, policies):
        raise NotImplementedError()

    def perform_op(self, a, b):
        op = BackupRetentionPolicyFilter.number_ops[self.data.get('op', 'eq')]
        return op(a, b)

    @staticmethod
    def get_sql_server_name(sql_server_id):
        parsed = parse_resource_id(sql_server_id)
        return parsed.get('name')


@SqlDatabase.filter_registry.register('short-term-backup-retention-policy')
class ShortTermBackupRetentionPolicyFilter(BackupRetentionPolicyFilter):

    schema = type_schema(
        'short-term-backup-retention-policy',
        required=['retention-period-days'],
        **{
            'op': {'enum': list(BackupRetentionPolicyFilter.number_ops.keys())},
            'retention-period-days': {'type': 'number'},
        },
    )

    def __init__(self, data, manager=None):
        super(ShortTermBackupRetentionPolicyFilter, self).__init__(
            'backup_short_term_retention_policies', data, manager)
        self.retention_period_days_limit = self.data.get('retention-period-days')

    def filter_with_policies(self, i, policies):
        try:
            for policy in policies:
                actual_retention_days = policy.get('retention_days')
                return self.perform_op(actual_retention_days, self.retention_period_days_limit)
        except CloudError as e:
            # TODO: is there a way to figure this out before trying to iterate through policies?
            if e.status_code == 404:
                return self.filter_without_policies(i)
            else:
                raise e

    def filter_without_policies(self, i):
        # without any backup retention policies, this is effectively 0 days of retention
        return self.perform_op(0, self.retention_period_days_limit)


@SqlDatabase.filter_registry.register('long-term-backup-retention-policy')
class LongTermBackupRetentionPolicyFilter(BackupRetentionPolicyFilter):

    @enum.unique
    class BackupType(enum.Enum):
        weekly = 'weekly'
        monthly = 'monthly'
        yearly = 'yearly'

        def __str__(self):
            return self.value

    @enum.unique
    class RetentionPeriodUnits(enum.Enum):
        days = ('days', 'D')
        weeks = ('weeks', 'W')
        months = ('months', 'M')
        years = ('years', 'Y')

        def __init__(self, str_value, iso8601_symbol):
            self.str_value = str_value
            self.iso8601_symbol = iso8601_symbol

        def __str__(self):
            return self.str_value

    schema = type_schema(
        'long-term-backup-retention-policy',
        required=['backup-type', 'retention-period', 'retention-period-units'],
        **{
            'backup-type': {'enum': list([str(t) for t in BackupType])},
            'op': {'enum': list(BackupRetentionPolicyFilter.number_ops.keys())},
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

    def filter_with_policies(self, i, policies):

        if self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.weekly.value:
            actual_retention_days_iso8601 = policies.weekly_retention
        elif self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.monthly.value:
            actual_retention_days_iso8601 = policies.monthly_retention
        elif self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.yearly.value:
            actual_retention_days_iso8601 = policies.yearly_retention
        else:
            raise ValueError("Unknown backup-type: {}".format(self.backup_type))

        # TODO figure out a better way to compare durations
        #
        # given ISO 8601 duration: P30D and P1M:
        #   in march : P30D > P1M
        #   in april : P30D = P1M
        #   in may   : P30D < P1M

        actual_duration = isodate.parse_duration(actual_retention_days_iso8601)
        actual_duration = LongTermBackupRetentionPolicyFilter.normalize_duration(actual_duration)
        result = self.perform_op(actual_duration, self.duration_limit)
        return result
