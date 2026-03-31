# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.filters.iampolicy import IamPolicyFilter
from c7n_gcp.provider import resources
from c7n_gcp.query import (
    QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo
)
from c7n.utils import local_session
from c7n_gcp.filters.timerange import TimeRangeFilter


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
        perm_service = 'bigtable'
        asset_type = "bigtableadmin.googleapis.com/Instance"
        default_report_fields = ['displayName', 'expireTime']
        labels = True
        labels_op = 'partialUpdateInstance'

        @staticmethod
        def get_label_params(resource, all_labels):
            return {
                'name': resource['name'],
                'updateMask': 'labels',
                'body': {'labels': all_labels},
            }


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
        asset_type = "bigtableadmin.googleapis.com/Cluster"

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
        asset_type = "bigtableadmin.googleapis.com/Backup"

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': '{}'.format(
                parent_instance['name'],
            )
        }


@BigTableInstanceClusterBackup.filter_registry.register('time-range')
class TimeRange(TimeRangeFilter):
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
    create_time_field_name = 'startTime'
    expire_time_field_name = 'expireTime'
    permissions = ('bigtable.backups.list',)


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
        asset_type = "bigtableadmin.googleapis.com/Table"

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
