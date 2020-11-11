# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
import enum
import logging

from azure.mgmt.sql.models import BackupLongTermRetentionPolicy, DatabaseUpdate, Sku
from msrestazure.azure_exceptions import CloudError

from c7n.filters import Filter
from c7n.filters.core import PolicyValidationError
from c7n.utils import get_annotation_prefix, type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.filters import scalar_ops
from c7n_azure.provider import resources
from c7n_azure.query import ChildTypeInfo
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser, RetentionPeriod, ThreadHelper

log = logging.getLogger('custodian.azure.sqldatabase')


@resources.register('sql-database', aliases=['sqldatabase'])
class SqlDatabase(ChildArmResourceManager):
    """SQL Server Database Resource

    The ``azure.sqldatabase`` resource is a child resource of the SQL Server resource,
    and the SQL Server parent id is available as the ``c7n:parent-id`` property.

    :example:

    Finds all SQL Servers Database in the subscription.

    .. code-block:: yaml

        policies:
            - name: find-all-sql-databases
              resource: azure.sqldatabase

    """
    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('databases', 'list_by_server', None)
        parent_manager_name = 'sqlserver'
        resource_type = 'Microsoft.Sql/servers/databases'
        enable_tag_operations = False  # GH Issue #4543
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.[name, tier, capacity, family]',
            '"c7n:parent-id"'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {'resource_group_name': parent_resource['resourceGroup'],
                    'server_name': parent_resource['name']}


class BackupRetentionPolicyHelper:

    SHORT_TERM_SQL_OPERATIONS = 'backup_short_term_retention_policies'
    LONG_TERM_SQL_OPERATIONS = 'backup_long_term_retention_policies'

    WEEK_OF_YEAR = 'week_of_year'

    @enum.unique
    class LongTermBackupType(enum.Enum):
        weekly = ('weekly_retention',)
        monthly = ('monthly_retention',)
        yearly = ('yearly_retention',)

        def __init__(self, retention_property):
            self.retention_property = retention_property

        def get_retention_from_backup_policy(self, backup_policy):
            return backup_policy[self.retention_property]

        def __str__(self):
            return self.name

    @staticmethod
    def get_backup_retention_policy_context(database):
        server_id = database[ChildTypeInfo.parent_key]
        resource_group_name = database['resourceGroup']
        database_name = database['name']
        server_name = ResourceIdParser.get_resource_name(server_id)

        return resource_group_name, server_name, database_name

    @staticmethod
    def get_backup_retention_policy(database, get_operation, cache_key):

        policy_key = get_annotation_prefix(cache_key)
        cached_policy = database.get(policy_key)
        if cached_policy:
            return cached_policy

        resource_group_name, server_name, database_name = \
            BackupRetentionPolicyHelper.get_backup_retention_policy_context(database)

        try:
            response = get_operation(resource_group_name, server_name, database_name)
        except CloudError as e:
            if e.status_code == 404:
                return None
            else:
                log.error(
                    "Unable to get backup retention policy. "
                    "(resourceGroup: {}, sqlserver: {}, sqldatabase: {})".format(
                        resource_group_name, server_name, database_name
                    )
                )
                raise e

        retention_policy = response.as_dict()
        database[policy_key] = retention_policy
        return retention_policy


class BackupRetentionPolicyBaseFilter(Filter, metaclass=abc.ABCMeta):

    schema = type_schema(
        'backup-retention-policy',
        **{
            'op': {'enum': list(scalar_ops.keys())}
        }
    )

    def __init__(self, operations_property, retention_limit, data, manager=None):
        super(BackupRetentionPolicyBaseFilter, self).__init__(data, manager)
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
        retention_policy = BackupRetentionPolicyHelper.get_backup_retention_policy(
            resource, get_operation, self.operations_property)
        if retention_policy is None:
            return self._perform_op(0, self.retention_limit)
        retention = self.get_retention_from_backup_policy(retention_policy)
        return retention is not None and self._perform_op(retention, self.retention_limit)

    def _perform_op(self, a, b):
        op = scalar_ops.get(self.data.get('op', 'eq'))
        return op(a, b)


@SqlDatabase.filter_registry.register('short-term-backup-retention-policy')
@SqlDatabase.filter_registry.register('short-term-backup-retention')
class ShortTermBackupRetentionPolicyFilter(BackupRetentionPolicyBaseFilter):
    """

    Filter SQL Databases on the length of their short term backup retention policies.

    If the database has no backup retention policies, the database is treated as if
    it has a backup retention of zero days.

    :example:

    Find all SQL Databases with a short term retention policy shorter than 2 weeks.

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
        aliases=['short-term-backup-retention'],
        required=['retention-period-days'],
        rinherit=BackupRetentionPolicyBaseFilter.schema,
        **{
            'retention-period-days': {'type': 'number'}
        }
    )

    def __init__(self, data, manager=None):
        retention_limit = data.get('retention-period-days')
        super(ShortTermBackupRetentionPolicyFilter, self).__init__(
            BackupRetentionPolicyHelper.SHORT_TERM_SQL_OPERATIONS, retention_limit, data, manager)

    def get_retention_from_backup_policy(self, retention_policy):
        return retention_policy['retention_days']


@SqlDatabase.filter_registry.register('long-term-backup-retention-policy')
@SqlDatabase.filter_registry.register('long-term-backup-retention')
class LongTermBackupRetentionPolicyFilter(BackupRetentionPolicyBaseFilter):
    """

    Filter SQL Databases on the length of their long term backup retention policies.

    There are 3 backup types for a sql database: weekly, monthly, and yearly. And, each
    of these backups has a retention period that can specified in units of days, weeks,
    months, or years.

    :example:

    Find all SQL Databases with weekly backup retentions longer than 1 month.

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

    schema = type_schema(
        'long-term-backup-retention-policy',
        aliases=['long-term-backup-retention'],
        required=['backup-type', 'retention-period', 'retention-period-units'],
        rinherit=BackupRetentionPolicyBaseFilter.schema,
        **{
            'backup-type': {
                'enum': list([t.name for t in BackupRetentionPolicyHelper.LongTermBackupType])
            },
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
            BackupRetentionPolicyHelper.LONG_TERM_SQL_OPERATIONS, retention_period, data, manager)
        self.backup_type = BackupRetentionPolicyHelper.LongTermBackupType[self.data.get(
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


class BackupRetentionPolicyBaseAction(AzureBaseAction, metaclass=abc.ABCMeta):

    def __init__(self, operations_property, *args, **kwargs):
        super(BackupRetentionPolicyBaseAction, self).__init__(*args, **kwargs)
        self.operations_property = operations_property

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, database):
        update_operation = getattr(self.client, self.operations_property).create_or_update

        resource_group_name, server_name, database_name = \
            BackupRetentionPolicyHelper.get_backup_retention_policy_context(database)
        parameters = self._get_parameters_for_new_retention_policy(database)

        new_retention_policy = update_operation(
            resource_group_name, server_name, database_name, parameters).result()

        # Update the cached version
        database[get_annotation_prefix(self.operations_property)] = new_retention_policy.as_dict()

    @abc.abstractmethod
    def _get_parameters_for_new_retention_policy(self, database):
        raise NotImplementedError()


@SqlDatabase.action_registry.register('update-short-term-backup-retention-policy')
@SqlDatabase.action_registry.register('update-short-term-backup-retention')
class ShortTermBackupRetentionPolicyAction(BackupRetentionPolicyBaseAction):
    """

    Update the short term backup retention policy for a SQL Database.

    :example:

    Update any SQL Database short term retentions to at least 7 days.

    .. code-block:: yaml

            policies:
              - name: update-short-term-backup-retention-policy
                resource: azure.sqldatabase
                filters:
                  - type: short-term-backup-retention-policy
                    op: lt
                    retention-period-days: 7
                actions:
                  - type: update-short-term-backup-retention-policy
                    retention-period-days: 7

    """

    VALID_RETENTION_PERIOD_DAYS = [7, 14, 21, 28, 35]

    schema = type_schema(
        'update-short-term-backup-retention-policy',
        aliases=['update-short-term-backup-retention'],
        rinherit=ShortTermBackupRetentionPolicyFilter.schema,
        op=None
    )

    def __init__(self, *args, **kwargs):
        super(ShortTermBackupRetentionPolicyAction, self).__init__(
            BackupRetentionPolicyHelper.SHORT_TERM_SQL_OPERATIONS, *args, **kwargs)
        self.retention_period_days = self.data['retention-period-days']

    def validate(self):
        if self.retention_period_days not in \
                ShortTermBackupRetentionPolicyAction.VALID_RETENTION_PERIOD_DAYS:
            raise PolicyValidationError(
                "Invalid retention-period-days: {}. Valid values are: {}".format(
                    self.retention_period_days,
                    ShortTermBackupRetentionPolicyAction.VALID_RETENTION_PERIOD_DAYS
                )
            )
        return self

    def _get_parameters_for_new_retention_policy(self, database):
        return self.retention_period_days


@SqlDatabase.action_registry.register('update-long-term-backup-retention-policy')
@SqlDatabase.action_registry.register('update-long-term-backup-retention')
class LongTermBackupRetentionPolicyAction(BackupRetentionPolicyBaseAction):
    """

    Update the long term backup retention policy for a SQL Database.

    There are 3 backup types for a sql database: weekly, monthly, and yearly. And, each
    of these backups has a retention period that can specified in units of days, weeks,
    months, or years.

    :example:

    Enforce a 1 month maximum retention for weekly backups on all SQL Databases

    .. code-block:: yaml

            policies:
              - name: update-long-term-backup-retention-policy
                resource: azure.sqldatabase
                filters:
                  - type: long-term-backup-retention-policy
                    backup-type: weekly
                    op: gt
                    retention-period: 1
                    retention-period-units: months
                actions:
                  - type: update-long-term-backup-retention-policy
                    backup-type: weekly
                    retention-period: 1
                    retention-period-units: months

    """

    schema = type_schema(
        'update-long-term-backup-retention-policy',
        aliases=['update-long-term-backup-retention'],
        rinherit=LongTermBackupRetentionPolicyFilter.schema,
        op=None
    )

    def __init__(self, *args, **kwargs):
        super(LongTermBackupRetentionPolicyAction, self).__init__(
            BackupRetentionPolicyHelper.LONG_TERM_SQL_OPERATIONS, *args, **kwargs)

        self.backup_type = BackupRetentionPolicyHelper.LongTermBackupType[self.data.get(
            'backup-type')]
        retention_period = self.data['retention-period']
        retention_period_units = RetentionPeriod.Units[self.data['retention-period-units']]
        self.iso8601_duration = RetentionPeriod.iso8601_duration(
            retention_period,
            retention_period_units
        )

    def _get_parameters_for_new_retention_policy(self, database):
        get_retention_policy_operation = getattr(self.client, self.operations_property).get
        current_retention_policy = BackupRetentionPolicyHelper.get_backup_retention_policy(database,
            get_retention_policy_operation, self.operations_property)

        new_retention_policy = self._copy_retention_policy(current_retention_policy) \
            if current_retention_policy else {}
        new_retention_policy[self.backup_type.retention_property] = self.iso8601_duration

        # Make sure that the week_of_year is set properly based on what
        # the yearly backup retention is. If this is not done, the API will
        # fail with an invalid parameter value
        yearly_retention = new_retention_policy.get(
            BackupRetentionPolicyHelper.LongTermBackupType.yearly.retention_property
        )
        week_of_year = new_retention_policy.get(BackupRetentionPolicyHelper.WEEK_OF_YEAR)
        if yearly_retention is None:
            # Without a yearly retention, the week should be 0
            new_retention_policy[BackupRetentionPolicyHelper.WEEK_OF_YEAR] = 0
        elif not week_of_year:
            # If there is a yearly retention, and the week is not specified, default to week 1
            new_retention_policy[BackupRetentionPolicyHelper.WEEK_OF_YEAR] = 1

        return BackupLongTermRetentionPolicy(**new_retention_policy)

    def _copy_retention_policy(self, retention_policy):
        """
        Create a copy of a retention policy object with only the required parameters for the
        BackupLongTermRetentionPolicy class.

        more info:
          https://docs.microsoft.com/en-us/python/api/azure-mgmt-sql/azure.mgmt.sql.models.backuplongtermretentionpolicy?view=azure-python
        """

        keys = [backup_type.retention_property for backup_type in
            BackupRetentionPolicyHelper.LongTermBackupType]
        new_retention_policy = {key: retention_policy[key] for key in keys}

        new_retention_policy[BackupRetentionPolicyHelper.WEEK_OF_YEAR] = \
            retention_policy[BackupRetentionPolicyHelper.WEEK_OF_YEAR]
        return new_retention_policy


@SqlDatabase.action_registry.register('resize')
class Resize(AzureBaseAction):
    """
    Action to scale database.
    Required arguments: capacity in DTUs and tier (Basic, Standard or Premium).
    Max data size (in bytes) is optional.

    :example:

    This policy will resize database to Premium tier with 500 DTU and set max data size to 750 GB

    .. code-block:: yaml

        policies:
          - name: resize-db
            resource: azure.sqldatabase
            filters:
              - type: value
                key: name
                value: cctestdb
            actions:
              - type: resize
                tier: Premium
                capacity: 500
                max_size_bytes: 805306368000

    """

    schema = type_schema(
        'resize',
        required=['capacity', 'tier'],
        **{
            'capacity': {'type': 'number'},
            'tier': {'enum': ['Basic', 'Standard', 'Premium']},
            'max_size_bytes': {'type': 'number'}
        })

    def __init__(self, data, manager=None):
        super(Resize, self).__init__(data, manager)
        self.capacity = self.data['capacity']
        self.tier = self.data['tier']
        self.max_size_bytes = self.data.get('max_size_bytes', 0)

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, database):
        sku = Sku(capacity=self.capacity, tier=self.tier, name=self.tier)
        max_size_bytes = self.max_size_bytes if not 0 else database['properties']['maxSizeBytes']
        self.client.databases.update(
            database['resourceGroup'],
            ResourceIdParser.get_resource_name(database['c7n:parent-id']),
            database['name'],
            DatabaseUpdate(sku=sku, max_size_bytes=max_size_bytes)
        )
