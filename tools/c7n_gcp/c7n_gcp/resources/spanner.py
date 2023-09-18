# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema, local_session
from c7n_gcp.actions import MethodAction, SetIamPolicy
from c7n_gcp.filters import IamPolicyFilter, TimeRangeFilter
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager


@resources.register('spanner-instance')
class SpannerInstance(QueryResourceManager):
    """
    https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances
    """
    class resource_type(TypeInfo):
        service = 'spanner'
        version = 'v1'
        component = 'projects.instances'
        enum_spec = ('list', 'instances[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = [
            "name", "displayName", "nodeCount", "state", "config"]
        labels = True
        labels_op = 'patch'
        asset_type = "spanner.googleapis.com/Instance"
        metric_key = "resource.labels.instance_id"
        urn_component = "instance"
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['resourceName']}
            )

        @staticmethod
        def get_label_params(resource, all_labels):
            return {'name': resource['name'],
                    'body': {
                        'instance': {
                            'labels': all_labels
                        },
                        'field_mask': ', '.join(['labels'])}}


@resources.register('spanner-backup')
class SpannerInstanceBackup(ChildResourceManager):
    """GC resource: https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.backups"""
    class resource_type(ChildTypeInfo):
        service = 'spanner'
        version = 'v1'
        component = 'projects.instances.backups'
        enum_spec = ('list', 'backups[]', None)
        scope = 'parent'
        name = id = 'name'
        parent_spec = {
            'resource': 'spanner-instance',
            'child_enum_params': {
                ('instances', 'parent')},
            'use_child_query': True,
        }
        default_report_fields = ['name', 'expireTime']
        permissions = ('spanner.backups.list',)
        asset_type = 'spanner.googleapis.com/Backup'

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': 'projects/{}/instances/{}'.format(
                local_session(self.session_factory).get_default_project(),
                parent_instance['displayName'],
            )
        }


@SpannerInstanceBackup.filter_registry.register('time-range')
class SpannerInstanceBackupTimeRangeFilter(TimeRangeFilter):
    """Filters spanner instance backups based on a time range

    .. code-block:: yaml

        policies:
          - name: spanner_backup_expiration_time_30_days_or_more
            description: |
              Cloud Spanner backup is created with an expiration date of 29 days or less
            resource: gcp.spanner-backup
            filters:
              - type: time-range
                value: 29
    """
    permissions = ('spanner.backups.list',)
    create_time_field_name = 'createTime'
    expire_time_field_name = 'expireTime'


@SpannerInstanceBackup.filter_registry.register('iam-policy')
class SpannerInstanceBackupIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process spanner instance backup resources correctly.
    """
    permissions = ('spanner.backups.getIamPolicy',)


@SpannerInstance.filter_registry.register('iam-policy')
class SpannerInstanceIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process spanner instance resources correctly.
    """
    permissions = ('spanner.instances.getIamPolicy',)


@SpannerInstance.action_registry.register('delete')
class SpannerInstanceDelete(MethodAction):
    """The action is used for spanner instances delete.

    GCP action is https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances/delete

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-spanner-instances-delete
            resource: gcp.spanner-instance
            filters:
              - type: value
                key: nodeCount
                op: gte
                value: 2
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}


@SpannerInstance.action_registry.register('set')
class SpannerInstancePatch(MethodAction):
    """The action is used for spanner instances nodeCount patch.

    GCP action is https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances/patch

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-spanner-instances-change-node-count
            resource: gcp.spanner-instance
            filters:
              - type: value
                key: nodeCount
                op: gte
                value: 2
            actions:
              - type: set
                nodeCount: 1
    """
    schema = type_schema('set', required=['nodeCount'],
                         **{'nodeCount': {'type': 'number'}})
    method_spec = {'op': 'patch'}
    method_perm = 'update'

    def get_resource_params(self, model, resource):
        result = {'name': resource['name'],
                  'body': {
                      'instance': {
                          'nodeCount': self.data['nodeCount']
                      },
                      'field_mask': ', '.join(['nodeCount'])}
                  }
        return result


SpannerInstance.action_registry.register('set-iam-policy', SetIamPolicy)


@resources.register('spanner-database-instance')
class SpannerDatabaseInstance(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.databases
    """
    def _get_parent_resource_info(self, child_instance):
        resource_name = None
        if child_instance['name'] is not None:
            resource_names = child_instance['name'].split('/databases')
            if len(resource_names) > 0:
                resource_name = resource_names[0]
        return {
            'resourceName': resource_name
        }

    class resource_type(ChildTypeInfo):
        service = 'spanner'
        version = 'v1'
        component = 'projects.instances.databases'
        enum_spec = ('list', 'databases[]', None)
        name = id = 'name'
        scope = None
        parent_spec = {
            'resource': 'spanner-instance',
            'child_enum_params': [
                ('name', 'parent')
            ]
        }
        default_report_fields = ["name", "state", "createTime"]
        asset_type = "spanner.googleapis.com/Database"
        urn_component = "database"
        urn_id_segments = (3, 5)

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {
                    'name': resource_info['resourceName']}
            )


@SpannerDatabaseInstance.filter_registry.register('iam-policy')
class SpannerDatabaseInstanceIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process spanner database resources correctly.
    """
    permissions = ('spanner.databases.getIamPolicy',)


SpannerDatabaseInstance.action_registry.register('set-iam-policy', SetIamPolicy)


@SpannerDatabaseInstance.action_registry.register('delete')
class SpannerDatabaseInstanceDropDatabase(MethodAction):
    """The action is used for databases deleting.

    GCP action is https://cloud.google.com/spanner/docs
        /reference/rest/v1/projects.instances.databases/dropDatabase.

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-spanner-instance-databases-delete
            resource: gcp.spanner-database-instance
            filters:
              - type: value
                key: name
                op: contains
                value: dev
            actions:
              - type: delete
    """
    schema = type_schema('dropDatabase', **{'type': {'enum': ['delete']}})
    method_spec = {'op': 'dropDatabase'}
    method_perm = 'drop'

    def get_resource_params(self, model, resource):
        return {'database': resource['name']}
