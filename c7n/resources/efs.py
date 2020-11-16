# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action, BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters import Filter
from c7n.manager import resources
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.query import QueryResourceManager, ChildResourceManager, TypeInfo
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema, get_retry
from .aws import shape_validate


@resources.register('efs')
class ElasticFileSystem(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'efs'
        enum_spec = ('describe_file_systems', 'FileSystems', None)
        id = 'FileSystemId'
        name = 'Name'
        date = 'CreationTime'
        dimension = 'FileSystemId'
        arn_type = 'file-system'
        permission_prefix = arn_service = 'elasticfilesystem'
        filter_name = 'FileSystemId'
        filter_type = 'scalar'
        universal_taggable = True
        cfn_type = 'AWS::EFS::FileSystem'

    augment = universal_augment


@resources.register('efs-mount-target')
class ElasticFileSystemMountTarget(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'efs'
        parent_spec = ('efs', 'FileSystemId', None)
        enum_spec = ('describe_mount_targets', 'MountTargets', None)
        permission_prefix = 'elasticfilesystem'
        name = id = 'MountTargetId'
        filter_name = 'MountTargetId'
        filter_type = 'scalar'
        arn = False
        cfn_type = 'AWS::EFS::MountTarget'


@ElasticFileSystemMountTarget.filter_registry.register('subnet')
class Subnet(SubnetFilter):

    RelatedIdsExpression = "SubnetId"


@ElasticFileSystemMountTarget.filter_registry.register('security-group')
class SecurityGroup(SecurityGroupFilter):

    efs_group_cache = None

    RelatedIdsExpression = ""

    def get_related_ids(self, resources):

        if self.efs_group_cache:
            group_ids = set()
            for r in resources:
                group_ids.update(
                    self.efs_group_cache.get(r['MountTargetId'], ()))
            return list(group_ids)

        client = local_session(self.manager.session_factory).client('efs')
        groups = {}
        group_ids = set()
        retry = get_retry(('Throttled',), 12)

        for r in resources:
            groups[r['MountTargetId']] = retry(
                client.describe_mount_target_security_groups,
                MountTargetId=r['MountTargetId'])['SecurityGroups']
            group_ids.update(groups[r['MountTargetId']])

        self.efs_group_cache = groups
        return list(group_ids)


@ElasticFileSystem.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    """
    Filter a resource by its associcated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

        .. code-block:: yaml

            policies:
                - name: efs-kms-key-filters
                  resource: efs
                  filters:
                    - type: kms-key
                      key: c7n:AliasName
                      value: "^(alias/aws/)"
                      op: regex
    """
    RelatedIdsExpression = 'KmsKeyId'


@ElasticFileSystem.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('elasticfilesystem:DescribeMountTargets',
                   'elasticfilesystem:DeleteMountTarget',
                   'elasticfilesystem:DeleteFileSystem')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('efs')
        self.unmount_filesystems(resources)
        retry = get_retry(('FileSystemInUse',), 12)
        for r in resources:
            retry(client.delete_file_system, FileSystemId=r['FileSystemId'])

    def unmount_filesystems(self, resources):
        client = local_session(self.manager.session_factory).client('efs')
        for r in resources:
            if not r['NumberOfMountTargets']:
                continue
            for t in client.describe_mount_targets(
                    FileSystemId=r['FileSystemId'])['MountTargets']:
                client.delete_mount_target(MountTargetId=t['MountTargetId'])


@ElasticFileSystem.action_registry.register('configure-lifecycle-policy')
class ConfigureLifecycle(BaseAction):
    """Enable/disable lifecycle policy for efs.

    :example:

      .. code-block:: yaml

            policies:
              - name: efs-apply-lifecycle
                resource: efs
                actions:
                  - type: configure-lifecycle-policy
                    state: enable
                    rules:
                      - 'TransitionToIA': 'AFTER_7_DAYS'

    """
    schema = type_schema(
        'configure-lifecycle-policy',
        state={'enum': ['enable', 'disable']},
        rules={
            'type': 'array',
            'items': {'type': 'object'}},
        required=['state'])

    permissions = ('elasticfilesystem:PutLifecycleConfiguration',)
    shape = 'PutLifecycleConfigurationRequest'

    def validate(self):
        if self.data.get('state') == 'enable' and 'rules' not in self.data:
            raise PolicyValidationError(
                'rules are required to enable lifecycle configuration %s' % (self.manager.data))
        if self.data.get('state') == 'disable' and 'rules' in self.data:
            raise PolicyValidationError(
                'rules not required to disable lifecycle configuration %s' % (self.manager.data))
        if self.data.get('rules'):
            attrs = {}
            attrs['LifecyclePolicies'] = self.data['rules']
            attrs['FileSystemId'] = 'PolicyValidator'
            return shape_validate(attrs, self.shape, 'efs')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('efs')
        op_map = {'enable': self.data.get('rules'), 'disable': []}
        for r in resources:
            try:
                client.put_lifecycle_configuration(
                    FileSystemId=r['FileSystemId'],
                    LifecyclePolicies=op_map.get(self.data.get('state')))
            except client.exceptions.FileSystemNotFound:
                continue


@ElasticFileSystem.filter_registry.register('lifecycle-policy')
class LifecyclePolicy(Filter):
    """Filters efs based on the state of lifecycle policies

    :example:

      .. code-block:: yaml

            policies:
              - name: efs-filter-lifecycle
                resource: efs
                filters:
                  - type: lifecycle-policy
                    state: present
                    value: AFTER_7_DAYS

    """
    schema = type_schema(
        'lifecycle-policy',
        state={'enum': ['present', 'absent']},
        value={'type': 'string'},
        required=['state'])

    permissions = ('elasticfilesystem:DescribeLifecycleConfiguration',)

    def process(self, resources, event=None):
        resources = self.fetch_resources_lfc(resources)
        if self.data.get('value'):
            config = {'TransitionToIA': self.data.get('value')}
            if self.data.get('state') == 'present':
                return [r for r in resources if config in r.get('c7n:LifecyclePolicies')]
            return [r for r in resources if config not in r.get('c7n:LifecyclePolicies')]
        else:
            if self.data.get('state') == 'present':
                return [r for r in resources if r.get('c7n:LifecyclePolicies')]
            return [r for r in resources if r.get('c7n:LifecyclePolicies') == []]

    def fetch_resources_lfc(self, resources):
        client = local_session(self.manager.session_factory).client('efs')
        for r in resources:
            try:
                lfc = client.describe_lifecycle_configuration(
                    FileSystemId=r['FileSystemId']).get('LifecyclePolicies')
                r['c7n:LifecyclePolicies'] = lfc
            except client.exceptions.FileSystemNotFound:
                continue
        return resources
