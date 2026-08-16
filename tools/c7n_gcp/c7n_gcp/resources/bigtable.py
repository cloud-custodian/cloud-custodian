# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.filters.iampolicy import IamPolicyFilter
from c7n_gcp.provider import resources
from c7n_gcp.query import (
    QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo
)
from c7n.utils import local_session, type_schema
from c7n_gcp.filters.timerange import TimeRangeFilter
from c7n.filters.core import ValueFilter


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
        labels_perm = 'update'

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
    table_detail_annotation_key = 'c7n:table-detail'

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

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {'name': resource_info['name']})

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': 'projects/{}/instances/{}'.format(
                local_session(self.session_factory).get_default_project(),
                parent_instance['displayName'],
            )
        }

    def get_table_detail(self, resource):
        annotation_key = self.table_detail_annotation_key
        client = self.get_client()
        detail = self.resource_type.get(client, resource)
        resource[annotation_key] = detail
        return detail

    def enrich_table_details(self, resources):
        for resource in resources:
            self.get_table_detail(resource)

        return resources


@BigTableInstanceTable.filter_registry.register('iam-policy')
class BigTableInstanceTableIamPolicyFilter(IamPolicyFilter):
    permissions = ('resourcemanager.projects.getIamPolicy',)


@BigTableInstanceTable.filter_registry.register('gc-rule')
class BigTableInstanceTableGcRuleFilter(ValueFilter):
    """Filter Bigtable tables by GC rule fields from table detail payloads.

    This filter evaluates against the table `get` response, allowing value
    expressions that reference `columnFamilies`.

    .. code-block:: yaml

        policies:
          - name: bigtable-table-gc-rules
            resource: gcp.bigtable-instance-table
            filters:
              - type: gc-rule
                key: columnFamilies.*.gcRule.maxAge
                op: ne
                value: null
    """

    schema = type_schema('gc-rule', rinherit=ValueFilter.schema)
    permissions = ('bigtable.tables.get',)

    def process(self, resources, event=None):
        annotation_key = self.manager.table_detail_annotation_key
        self.manager.enrich_table_details(resources)
        return [r for r in resources if self.match(r[annotation_key])]
