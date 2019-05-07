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

import abc
import six
import logging
import enum
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager
from c7n_azure.query import ChildResourceQuery
from c7n_azure.filters import scalar_ops
from c7n.filters import Filter
from c7n_azure.utils import RetentionPeriod, ResourceIdParser, ThreadHelper
from c7n.utils import type_schema
from msrestazure.azure_exceptions import CloudError

log = logging.getLogger('custodian.azure.sqldatabase')


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


@six.add_metaclass(abc.ABCMeta)
class BackupRetentionPolicyFilter(Filter):

    schema = type_schema(
        'backup-retention-policy',
        **{
            'op': {'enum': list(scalar_ops.keys())}
        }
    )

    def __init__(self, operations_property, retention_limit, data, manager=None):
        super(BackupRetentionPolicyFilter, self).__init__(data, manager)
        self.operations_property = operations_property
        self.retention_limit = retention_limit

    @abc.abstractmethod
    def get_retention_from_backup_policy(self, retention_policy):
        raise NotImplementedError()

    def process(self, resources, event=None):
        resources, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log
        )
        if exceptions:
            raise exceptions[0]
        return resources

    def _process_resource_set(self, resources, event):
        client = self.manager.get_client()
        get_operation = getattr(client, self.operations_property).get
        matched_resources = []

        for resource in resources:
            match = self._process_resource(resource, get_operation)
            if match:
                matched_resources.append(resource)
        return matched_resources

    def _process_resource(self, resource, get_operation):
        retention_policy = self._get_backup_retention_policy(resource, get_operation)
        resource['c7n:{}'.format(self.operations_property)] = retention_policy.as_dict()
        if retention_policy is None:
            return self._perform_op(0, self.retention_limit)
        retention = self.get_retention_from_backup_policy(retention_policy)
        return retention is not None and self._perform_op(retention, self.retention_limit)

    def _get_backup_retention_policy(self, resource, get_operation):
        server_id = resource[ChildResourceQuery.parent_key]
        resource_group_name = resource.get('resourceGroup')
        if resource_group_name is None:
            resource_group_name = ResourceIdParser.get_resource_group(server_id)
        database_name = resource['name']
        server_name = ResourceIdParser.get_resource_name(server_id)

        try:
            response = get_operation(resource_group_name, server_name, database_name)
        except CloudError as e:
            if e.status_code == 404:
                response = None
            else:
                log.error("Unable to get backup retention policy. "
                "(resourceGroup: {}, sqlserver: {}, sqldatabase: {})".format(
                    resource_group_name, server_name, database_name))
                raise e

        return response

    def _perform_op(self, a, b):
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

    def get_retention_from_backup_policy(self, retention_policy):
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
        weekly = ('weekly_retention',)
        monthly = ('monthly_retention',)
        yearly = ('yearly_retention',)

        def __init__(self, retention_property):
            self.retention_property = retention_property

        def get_retention_from_backup_policy(self, backup_policy):
            return getattr(backup_policy, self.retention_property)

        def __str__(self):
            return self.name

    schema = type_schema(
        'long-term-backup-retention-policy',
        required=['backup-type', 'retention-period', 'retention-period-units'],
        rinherit=BackupRetentionPolicyFilter.schema,
        **{
            'backup-type': {'enum': list([t.name for t in BackupType])},
            'retention-period': {'type': 'number'},
            'retention-period-units': {
                'enum': list([u.name for u in RetentionPeriod.Units])
            }
        }
    )

    def __init__(self, data, manager=None):
        retention_period = data.get('retention-period')
        self.retention_period_units = RetentionPeriod.Units[
            data.get('retention-period-units')]

        super(LongTermBackupRetentionPolicyFilter, self).__init__(
            'backup_long_term_retention_policies', retention_period, data, manager)
        self.backup_type = LongTermBackupRetentionPolicyFilter.BackupType[self.data.get(
            'backup-type')]

    def get_retention_from_backup_policy(self, retention_policy):
        actual_retention_iso8601 = self.backup_type.get_retention_from_backup_policy(
            retention_policy)

        try:
            actual_duration, actual_duration_units = RetentionPeriod.parse_iso8601_retention_period(
                actual_retention_iso8601)
        except ValueError:
            return None

        if actual_duration_units.iso8601_symbol != self.retention_period_units.iso8601_symbol:
            return None
        return actual_duration
