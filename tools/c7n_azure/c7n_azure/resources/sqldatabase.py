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
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager
from c7n_azure.query import ChildResourceQuery
from c7n_azure.filters import scalar_ops
from c7n.filters import Filter
from c7n_azure.utils import RetentionPeriodHelper
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
            'op': {'enum': list(scalar_ops.keys())}
        }
    )

    @staticmethod
    def get_sql_server_name(sql_server_id):
        parsed = parse_resource_id(sql_server_id)
        return parsed.get('name')

    def __init__(self, operations_property, retention_limit, data, manager=None):
        super(BackupRetentionPolicyFilter, self).__init__(data, manager)
        self.operations_property = operations_property
        self.retention_limit = retention_limit

    def get_backup_retention_policy(self, i):
        client = self.manager.get_client()
        get_operation = getattr(client, self.operations_property).get

        resource_group_name = i.get('resourceGroup')
        server_name = BackupRetentionPolicyFilter.get_sql_server_name(
            i.get(ChildResourceQuery.parent_key))
        database_name = i.get('name')

        try:
            response = get_operation(resource_group_name, server_name, database_name)
        except CloudError as e:
            if e.status_code == 404:
                response = None
            else:
                # TODO how to better handle this error?
                raise e
        return response

    def __call__(self, i):
        retention_policy = self.get_backup_retention_policy(i)
        if retention_policy is None:
            return self.perform_op(0, self.retention_limit)
        retention = self.get_retention_from_policy(retention_policy)
        return self.perform_op(retention, self.retention_limit)

    def get_retention_from_policy(self, retention_policy):
        raise NotImplementedError()

    def perform_op(self, a, b):
        op = scalar_ops.get(self.data.get('op', 'eq'))
        return op(a, b)


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
            'retention-period-days': {'type': 'number'}
        }
    )

    def __init__(self, data, manager=None):
        retention_limit = data.get('retention-period-days')
        super(ShortTermBackupRetentionPolicyFilter, self).__init__(
            'backup_short_term_retention_policies', retention_limit, data, manager)

    def get_retention_from_policy(self, retention_policy):
        return retention_policy.retention_days


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

    schema = type_schema(
        'long-term-backup-retention-policy',
        required=['backup-type', 'retention-period', 'retention-period-units'],
        rinherit=BackupRetentionPolicyFilter.schema,
        **{
            'backup-type': {'enum': list([str(t) for t in BackupType])},
            'retention-period': {'type': 'number'},
            'retention-period-units': {
                'enum': list([str(u) for u in RetentionPeriodHelper.RetentionPeriodUnits])
            }
        }
    )

    def __init__(self, data, manager=None):
        retention_period = data.get('retention-period')
        retention_period_units = RetentionPeriodHelper.RetentionPeriodUnits[
            data.get('retention-period-units')]
        retention_limit = RetentionPeriodHelper.period_to_duration_limit(
            retention_period, retention_period_units)

        super(LongTermBackupRetentionPolicyFilter, self).__init__(
            'backup_long_term_retention_policies', retention_limit, data, manager)
        self.backup_type = self.data.get('backup-type')

    def get_retention_from_policy(self, retention_policy):
        if self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.weekly.value:
            actual_retention_days_iso8601 = retention_policy.weekly_retention
        elif self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.monthly.value:
            actual_retention_days_iso8601 = retention_policy.monthly_retention
        elif self.backup_type == LongTermBackupRetentionPolicyFilter.BackupType.yearly.value:
            actual_retention_days_iso8601 = retention_policy.yearly_retention
        else:
            raise ValueError("Unknown backup-type: {}".format(self.backup_type))

        actual_duration = isodate.parse_duration(actual_retention_days_iso8601)
        actual_duration = RetentionPeriodHelper.normalize_duration(actual_duration)
        return actual_duration
