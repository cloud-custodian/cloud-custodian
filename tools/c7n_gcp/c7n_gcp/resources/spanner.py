# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError
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
        labels_perm = 'update'
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

        @staticmethod
        def get_metric_resource_name(resource, metric_key=None):
            # Extract instance name from the full resource name
            return resource["name"].split("/")[-1]


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
        allow_metrics_filters = False

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


@SpannerInstance.action_registry.register('set-autoscaling')
class SpannerInstanceSetAutoscaling(MethodAction):
    """Enable or update managed autoscaling on a Spanner instance.

    Limits are given either in nodes (``minNodes`` / ``maxNodes``) or in
    processing units (``minProcessingUnits`` / ``maxProcessingUnits``), not
    both. ``storageUtilizationPercent`` is required; the CPU targets are
    optional.

    The maximum can be at most 10 times the minimum.

    The whole ``autoscalingConfig`` is replaced, except that any existing
    ``asymmetricAutoscalingOptions`` on the instance are kept.

    Managed autoscaling requires the ENTERPRISE or ENTERPRISE_PLUS edition,
    so instances on any other edition are skipped with a warning.

    GCP action is https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances/patch

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-spanner-instance-enable-autoscaling
            resource: gcp.spanner-instance
            filters:
              - type: value
                key: instanceType
                value: PROVISIONED
              - type: value
                key: edition
                op: in
                value: [ENTERPRISE, ENTERPRISE_PLUS]
              - type: value
                key: autoscalingConfig
                value: absent
            actions:
              - type: set-autoscaling
                minNodes: 1
                maxNodes: 3
                highPriorityCpuUtilizationPercent: 65
                storageUtilizationPercent: 95
    """
    node_limits = ('minNodes', 'maxNodes')
    processing_unit_limits = ('minProcessingUnits', 'maxProcessingUnits')

    schema = type_schema(
        'set-autoscaling',
        required=['storageUtilizationPercent'],
        minNodes={'type': 'integer', 'minimum': 1},
        maxNodes={'type': 'integer', 'minimum': 1},
        minProcessingUnits={'type': 'integer', 'minimum': 1000, 'multipleOf': 1000},
        maxProcessingUnits={'type': 'integer', 'minimum': 1000, 'multipleOf': 1000},
        highPriorityCpuUtilizationPercent={'type': 'integer', 'minimum': 10, 'maximum': 90},
        totalCpuUtilizationPercent={'type': 'integer', 'minimum': 10, 'maximum': 90},
        storageUtilizationPercent={'type': 'integer', 'minimum': 10, 'maximum': 99},
    )
    method_spec = {'op': 'patch'}
    method_perm = 'update'
    # https://cloud.google.com/spanner/docs/managed-autoscaler
    attr_filter = ('edition', ('ENTERPRISE', 'ENTERPRISE_PLUS'))
    max_limit_ratio = 10

    def validate(self):
        has_nodes = any(k in self.data for k in self.node_limits)
        has_units = any(k in self.data for k in self.processing_unit_limits)
        if has_nodes == has_units:
            raise PolicyValidationError(
                f"{self.type} requires either {' / '.join(self.node_limits)} or "
                f"{' / '.join(self.processing_unit_limits)}, not both, on {self.manager.data}")
        low, high = self.node_limits if has_nodes else self.processing_unit_limits
        if low not in self.data or high not in self.data:
            raise PolicyValidationError(
                f"{self.type} requires both {low} and {high} on {self.manager.data}")
        if self.data[low] > self.data[high]:
            raise PolicyValidationError(
                f"{self.type} {low} must not exceed {high} on {self.manager.data}")
        if self.data[high] > self.max_limit_ratio * self.data[low]:
            raise PolicyValidationError(
                f"{self.type} {high} must not exceed {self.max_limit_ratio} times {low} "
                f"on {self.manager.data}")
        return self

    def get_resource_params(self, model, resource):
        limits = {k: self.data[k]
                  for k in self.node_limits + self.processing_unit_limits
                  if k in self.data}
        targets = {k: self.data[k]
                   for k in ('highPriorityCpuUtilizationPercent',
                             'totalCpuUtilizationPercent',
                             'storageUtilizationPercent')
                   if k in self.data}
        config = {'autoscalingLimits': limits, 'autoscalingTargets': targets}
        asymmetric = resource.get('autoscalingConfig', {}).get('asymmetricAutoscalingOptions')
        if asymmetric:
            config['asymmetricAutoscalingOptions'] = asymmetric
        return {'name': resource['name'],
                'body': {
                    'instance': {
                        'name': resource['name'],
                        'autoscalingConfig': config,
                    },
                    'fieldMask': 'autoscalingConfig'}}


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
        allow_metrics_filters = False

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
