# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import CrossAccountAccessFilter
from c7n.filters.policystatement import HasStatementFilter
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, NetworkLocation
from c7n.manager import resources
from c7n.query import (
    ChildResourceManager,
    DescribeSource,
    QueryResourceManager,
    TypeInfo,
)
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session


class DescribeFileSystem(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        for r in resources:
            r['Tags'] = [
                {'Key': t['key'], 'Value': t['value']}
                for t in r.pop('tags', [])]
        return resources


@resources.register('s3files-file-system')
class FileSystem(QueryResourceManager):
    """AWS S3 Files - File System

    An S3 Files file system provides file system interface access to
    the data of a backing general purpose S3 bucket.

    https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-files.html
    """

    class resource_type(TypeInfo):
        service = 's3files'
        enum_spec = ('list_file_systems', 'fileSystems', None)
        detail_spec = ('get_file_system', 'fileSystemId', 'fileSystemId', None)
        arn = 'fileSystemArn'
        id = 'fileSystemId'
        name = 'name'
        date = 'creationTime'
        cfn_type = 'AWS::S3Files::FileSystem'

    source_mapping = {'describe': DescribeFileSystem}


@resources.register('s3files-mount-target')
class MountTarget(ChildResourceManager):
    """AWS S3 Files - Mount Target

    Mount targets are the VPC network interfaces through which an
    S3 Files file system is reachable over NFS.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3files-mount-target-subnet
            resource: aws.s3files-mount-target
            filters:
              - type: subnet
                key: State
                value: available
    """

    class resource_type(TypeInfo):
        service = 's3files'
        parent_spec = ('s3files-file-system', 'fileSystemId', None)
        enum_spec = ('list_mount_targets', 'mountTargets', None)
        detail_spec = ('get_mount_target', 'mountTargetId', 'mountTargetId', None)
        name = id = 'mountTargetId'
        arn = False
        cfn_type = 'AWS::S3Files::MountTarget'


@MountTarget.filter_registry.register('subnet')
class MountTargetSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "subnetId"


@MountTarget.filter_registry.register('security-group')
class MountTargetSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "securityGroups[]"


MountTarget.filter_registry.register('network-location', NetworkLocation)


@resources.register('s3files-access-point')
class AccessPoint(ChildResourceManager):
    """AWS S3 Files - Access Point

    S3 Files access points are EFS-style entry points into a file
    system, pinning NFS clients to a POSIX identity and root
    directory. They carry no resource policy and no public access
    configuration; file system access is governed by the file system
    policy (see the ``cross-account`` and ``has-statement``
    filters on ``aws.s3files-file-system``).

    :example:

    .. code-block:: yaml

        policies:
          - name: s3files-access-point-root-user
            resource: aws.s3files-access-point
            filters:
              - type: value
                key: posixUser.uid
                value: 0
    """

    class resource_type(TypeInfo):
        service = 's3files'
        parent_spec = ('s3files-file-system', 'fileSystemId', None)
        enum_spec = ('list_access_points', 'accessPoints', None)
        arn = 'accessPointArn'
        id = 'accessPointId'
        name = 'name'
        cfn_type = 'AWS::S3Files::AccessPoint'


class FileSystemPolicyMixin:
    """Annotates file systems with their resource policy under c7n:Policy."""

    policy_attribute = 'c7n:Policy'

    def policy_annotate(self, client, resource):
        if self.policy_attribute in resource:
            return resource
        try:
            resp = client.get_file_system_policy(
                fileSystemId=resource['fileSystemId'])
            resource[self.policy_attribute] = resp.get('policy')
        except client.exceptions.ResourceNotFoundException:
            resource[self.policy_attribute] = None
        return resource


@FileSystem.filter_registry.register('cross-account')
class FileSystemCrossAccount(FileSystemPolicyMixin, CrossAccountAccessFilter):
    """Filter file systems whose policy grants access outside of
    allowed accounts or organizations.

    A file system without a policy does not evaluate IAM for NFS
    access at all; combine with ``has-statement`` to require a policy
    to be attached.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3files-cross-account
            resource: aws.s3files-file-system
            filters:
              - type: cross-account
                whitelist_orgids:
                  - o-xxxxxxxxxx
    """
    permissions = ('s3files:GetFileSystemPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('s3files')
        resources = [self.policy_annotate(client, r) for r in resources]
        return super().process(resources, event)


@FileSystem.filter_registry.register('has-statement')
class FileSystemHasStatement(FileSystemPolicyMixin, HasStatementFilter):
    """Find file systems with matching file system policy statements.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3files-require-secure-transport
            resource: aws.s3files-file-system
            filters:
              - type: has-statement
                statements:
                  - Effect: Deny
                    Condition:
                        Bool:
                            "aws:SecureTransport": "false"
    """
    permissions = ('s3files:GetFileSystemPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('s3files')
        resources = [self.policy_annotate(client, r) for r in resources]
        return super().process(resources, event)

    def get_std_format_args(self, fs):
        return {
            'file_system_arn': fs['fileSystemArn'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
        }


@FileSystem.action_registry.register('tag')
@AccessPoint.action_registry.register('tag')
class TagS3FilesResource(Tag):
    """Create tags on an S3 Files file system or access point.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3files-tag
            resource: aws.s3files-file-system
            actions:
              - type: tag
                key: owner
                value: data-platform
    """
    permissions = ('s3files:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = [{'key': t['Key'], 'value': t['Value']} for t in new_tags]
        id_key = self.manager.resource_type.id
        for r in resources:
            try:
                client.tag_resource(resourceId=r[id_key], tags=tags)
            except client.exceptions.ResourceNotFoundException:
                continue


@FileSystem.action_registry.register('remove-tag')
@AccessPoint.action_registry.register('remove-tag')
class RemoveTagS3FilesResource(RemoveTag):
    """Remove tags from an S3 Files file system or access point.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3files-remove-tag
            resource: aws.s3files-file-system
            actions:
              - type: remove-tag
                tags: ["expired-tag"]
    """
    permissions = ('s3files:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        id_key = self.manager.resource_type.id
        for r in resources:
            try:
                client.untag_resource(resourceId=r[id_key], tagKeys=tags)
            except client.exceptions.ResourceNotFoundException:
                continue


FileSystem.filter_registry.register('marked-for-op', TagActionFilter)
FileSystem.action_registry.register('mark-for-op', TagDelayedAction)
