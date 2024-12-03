# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from botocore.exceptions import ClientError

from c7n.actions import Action, BaseAction, RemovePolicyBase
from c7n.exceptions import PolicyValidationError
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters import Filter, CrossAccountAccessFilter
from c7n.manager import resources
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, NetworkLocation
from c7n.filters.policystatement import HasStatementFilter
from c7n.query import (
    QueryResourceManager, ChildResourceManager, TypeInfo, DescribeSource, ConfigSource
)
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema, get_retry
from .aws import shape_validate
from c7n.filters.backup import ConsecutiveAwsBackupsFilter


class EFSDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)


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
        config_type = cfn_type = 'AWS::EFS::FileSystem'
        arn = 'FileSystemArn'
        permissions_augment = ("elasticfilesystem:ListTagsForResource",)

    source_mapping = {
        'describe': EFSDescribe,
        'config': ConfigSource
    }


@resources.register('efs-mount-target')
class ElasticFileSystemMountTarget(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'efs'
        parent_spec = ('efs', 'FileSystemId', None)
        enum_spec = ('describe_mount_targets', 'MountTargets', None)
        permission_prefix = 'elasticfilesystem'
        name = id = 'MountTargetId'
        arn = False
        cfn_type = 'AWS::EFS::MountTarget'
        supports_trailevents = True


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


@ElasticFileSystemMountTarget.filter_registry.register('network-location', NetworkLocation)
@ElasticFileSystem.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

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


@ElasticFileSystem.filter_registry.register('check-secure-transport')
class CheckSecureTransport(Filter):
    """Find EFS that does not enforce secure transport

    :Example:

    .. code-block:: yaml

     - name: efs-securetransport-check-policy
       resource: efs
       filters:
         - check-secure-transport

    To configure an EFS to enforce secure transport, set up the appropriate
    Effect and Condition for its policy document. For example:

    .. code-block:: json

        {
            "Sid": "efs-statement-b3f6b59b-d938-4001-9154-508f67707073",
            "Effect": "Deny",
            "Principal": { "AWS": "*" },
            "Action": "*",
            "Condition": {
                "Bool": { "aws:SecureTransport": "false" }
            }
        }
    """

    schema = type_schema('check-secure-transport')
    permissions = ('elasticfilesystem:DescribeFileSystemPolicy',)

    policy_annotation = 'c7n:Policy'

    def get_policy(self, client, resource):
        if self.policy_annotation in resource:
            return resource[self.policy_annotation]
        try:
            result = client.describe_file_system_policy(
                FileSystemId=resource['FileSystemId'])
        except client.exceptions.PolicyNotFound:
            return None
        resource[self.policy_annotation] = json.loads(result['Policy'])
        return resource[self.policy_annotation]

    def securetransport_check_policy(self, client, resource):
        policy = self.get_policy(client, resource)
        if not policy:
            return True

        statements = policy['Statement']
        if isinstance(statements, dict):
            statements = [statements]

        for s in statements:
            try:
                effect = s['Effect']
                secureTransportValue = s['Condition']['Bool']['aws:SecureTransport']
                if ((effect == 'Deny' and secureTransportValue == 'false') or
                        (effect == 'Allow' and secureTransportValue == 'true')):
                    return False
            except (KeyError, TypeError):
                pass

        return True

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('efs')
        results = [r for r in resources if self.securetransport_check_policy(c, r)]
        self.log.info(
            "%d of %d EFS policies don't enforce secure transport",
            len(results), len(resources))
        return results


@ElasticFileSystem.filter_registry.register('has-statement')
class EFSHasStatementFilter(HasStatementFilter):

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.policy_attribute = 'c7n:Policy'

    def process(self, resources, event=None):
        resources = [self.policy_annotate(r) for r in resources]
        return super().process(resources, event)

    def policy_annotate(self, resource):
        client = local_session(self.manager.session_factory).client('efs')
        if self.policy_attribute in resource:
            return resource
        try:
            result = client.describe_file_system_policy(
                FileSystemId=resource['FileSystemId'])
            resource[self.policy_attribute] = result['Policy']
        except client.exceptions.PolicyNotFound:
            resource[self.policy_attribute] = None
            return resource
        return resource

    def get_std_format_args(self, fs):
        return {
            'fs_arn': fs['FileSystemArn'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region
        }


@ElasticFileSystem.filter_registry.register('cross-account')
class EFSCrossAccountFilter(CrossAccountAccessFilter):
    """Filter EFS file systems which have cross account permissions

    :example:

    .. code-block:: yaml

            policies:
              - name: efs-cross-account
                resource: aws.efs
                filters:
                  - type: cross-account
    """
    permissions = ('elasticfilesystem:DescribeFileSystemPolicy',)

    def process(self, resources, event=None):
        def _augment(r):
            client = local_session(
                self.manager.session_factory).client('efs')
            try:
                r['Policy'] = client.describe_file_system_policy(
                    FileSystemId=r['FileSystemId'])['Policy']
                return r
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.log.warning(
                        "Access denied getting policy elasticfilesystems:%s",
                        r['FileSystemId'])

        self.log.debug("fetching policy for %d elasticfilesystems" % len(resources))
        with self.executor_factory(max_workers=3) as w:
            resources = list(filter(None, w.map(_augment, resources)))

        return super(EFSCrossAccountFilter, self).process(
            resources, event)


@ElasticFileSystem.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from EFS

    :example:

    .. code-block:: yaml

           policies:
              - name: remove-efs-cross-account
                resource: efs
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    schema = type_schema(
        'remove-statements',
        required=['statement_ids'],
        statement_ids={'oneOf': [
            {'enum': ['matched']},
            {'type': 'array', 'items': {'type': 'string'}}]})

    permissions = (
        'elasticfilesystem:DescribeFileSystems', 'elasticfilesystem:DeleteFileSystemPolicy'
        )

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('efs')
        for r in resources:
            try:
                results += filter(None, [self.process_resource(client, r)])
            except Exception:
                self.log.exception(
                    "Error processing elasticfilesystem:%s", r['FileSystemId'])
        return results

    def process_resource(self, client, resource):
        if 'Policy' not in resource:
            try:
                resource['Policy'] = client.describe_file_system_policy(
                    FileSystemId=resource['FileSystemId']).get('Policy')
            except ClientError as e:
                if e.response['Error']['Code'] != "FileSystemNotFound":
                    raise

        if not resource['Policy']:
            return

        p = json.loads(resource['Policy'])
        statements, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)

        if not found:
            return

        if not statements:
            client.delete_file_system_policy(FileSystemId=resource['FileSystemId'])
        else:
            client.put_file_system_policy(
                FileSystemId=resource['FileSystemId'],
                Policy=json.dumps(p)
            )
        return {'Name': resource['FileSystemId'],
                'State': 'PolicyRemoved',
                'Statements': found}


ElasticFileSystem.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)
