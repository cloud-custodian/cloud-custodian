# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.filters.iampolicy import IamPolicyFilter
from c7n_gcp.provider import resources
from c7n_gcp.query import (
    QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo
)
from c7n.utils import local_session, type_schema
from c7n.filters import Filter
import datetime


@resources.register('bigtable-instance')
class BigTableInstance(QueryResourceManager):
    """GC resource:
    https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances"""
    class resource_type(TypeInfo):
        service = 'bigtableadmin'
        version = 'v2'
        component = 'projects.instances'
        enum_spec = ('list', 'instances[]', None)
        scope_key = 'parent'
        name = id = 'id'
        scope_template = "projects/{}"
        permissions = ('bigtable.instances.list',)
        default_report_fields = ['displayName', 'expireTime']


@resources.register('bigtable-instance-cluster')
class BigTableInstanceCluster(ChildResourceManager):
    """GC resource:
    https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.clusters"""
    class resource_type(ChildTypeInfo):
        service = 'bigtableadmin'
        version = 'v2'
        component = 'projects.instances.clusters'
        enum_spec = ('list', 'clusters[]', None)
        scope = 'parent'
        name = id = 'clusters'
        parent_spec = {
            'resource': 'bigtable-instance',
            'child_enum_params': {
                ('displayName', 'parent')},
            'use_child_query': True,
        }
        default_report_fields = ['name', 'expireTime']
        permissions = ('bigtable.clusters.list',)

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': 'projects/{}/instances/{}'.format(
                local_session(self.session_factory).get_default_project(),
                parent_instance['displayName'],
            )
        }


@resources.register('bigtable-instance-cluster-backup')
class BigTableInstanceClusterBackup(ChildResourceManager):
    """GC resource:
    https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.clusters.backups
    """
    class resource_type(ChildTypeInfo):
        service = 'bigtableadmin'
        version = 'v2'
        component = 'projects.instances.clusters.backups'
        enum_spec = ('list', 'backups[]', None)
        scope = 'parent'
        name = id = 'backups'
        parent_spec = {
            'resource': 'bigtable-instance-cluster',
            'child_enum_params': {
                ('name', 'parent')},
            'use_child_query': True,
        }
        default_report_fields = ['name', 'expireTime']
        permissions = ('bigtable.backups.list',)

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': '{}'.format(
                parent_instance['name'],
            )
        }


@BigTableInstanceClusterBackup.filter_registry.register('time-range')
class TimeRange(Filter):
    """Filters bigtable instance clusters backups based on a time range

    .. code-block:: yaml

        policies:
          - name: bigtable_backup_expiration_time_30_days
            description: |
              Cloud Bigtable backup expiration time is 29 days or less
            resource: gcp.bigtable-instance-cluster-backup
            filters:
              - type: time-range
                value: 29
    """
    schema = type_schema('time-range',
                         value={'$ref': '#/definitions/filters_common/value'})
    permissions = ('bigtable.backups.list',)

    datetime1_pattern = "%Y-%m-%dT%H:%M:%S.%fZ"
    datetime2_pattern = "%Y-%m-%dT%H:%M:%S"

    def process(self, resources, event=None):
        filtered_resources = []
        value = self.data.get('value')
        field1 = 'startTime'
        field2 = 'expireTime'
        for resource in resources:
            start_time_pattern = self.datetime1_pattern
            expired_time_pattern = self.datetime1_pattern
            expired_time = resource[field2]
            start_time = resource[field1]
            if '.' not in expired_time and 'Z' in expired_time:
                expired_time_pattern = self.datetime2_pattern
                expired_time = expired_time[:-1]
            if '.' not in start_time and 'Z' in start_time:
                start_time_pattern = self.datetime2_pattern
                start_time = start_time[:-1]

            filtered_expired_time = datetime.datetime.strptime(
                expired_time, expired_time_pattern)
            filtered_start_time = datetime.datetime.strptime(
                start_time, start_time_pattern)
            result_time = filtered_expired_time - filtered_start_time
            if int(result_time.days) < value:
                filtered_resources.append(resource)

        return filtered_resources


@resources.register('bigtable-instance-table')
class BigTableInstanceTable(ChildResourceManager):
    """ GC resource:
    https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.tables"""
    class resource_type(ChildTypeInfo):
        service = 'bigtableadmin'
        version = 'v2'
        component = 'projects.instances.tables'
        enum_spec = ('list', 'tables[]', None)
        scope = 'parent'
        name = id = 'name'
        parent_spec = {
            'resource': 'bigtable-instance',
            'child_enum_params': {
                ('name', 'parent')},
            'use_child_query': True,
        }
        default_report_fields = ['name']
        permissions = ('bigtable.tables.list',)

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': 'projects/{}/instances/{}'.format(
                local_session(self.session_factory).get_default_project(),
                parent_instance['displayName'],
            )
        }


@BigTableInstanceTable.filter_registry.register('iam-policy')
class BigTableInstanceTableIamPolicyFilter(IamPolicyFilter):
    permissions = ('resourcemanager.projects.getIamPolicy',)
