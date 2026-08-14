# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from datetime import datetime, timedelta

from c7n.manager import resources
from c7n.query import (
    QueryResourceManager, TypeInfo, DescribeSource, RetryPageIterator,
    DescribeWithResourceTags)
from c7n.actions import BaseAction
from c7n.tags import Tag, TagDelayedAction, RemoveTag, coalesce_copy_user_tags, TagActionFilter
from c7n.utils import type_schema, local_session, chunks, group_by, get_retry
from c7n.filters import Filter, ListItemFilter, MetricsFilter, ValueFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.vpc import (
    SecurityGroupFilter, SubnetFilter, VpcFilter, NetworkLocation)
from c7n.filters.backup import ConsecutiveAwsBackupsFilter


class DescribeFSx(DescribeSource):

    def get_resources(self, ids):
        """Support server side filtering on arns
        """
        for n in range(len(ids)):
            if ids[n].startswith('arn:'):
                ids[n] = ids[n].rsplit('/', 1)[-1]
        params = {'FileSystemIds': ids}
        return self.query.filter(self.manager, **params)


@resources.register('fsx')
class FSx(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'fsx'
        enum_spec = ('describe_file_systems', 'FileSystems', None)
        name = id = 'FileSystemId'
        arn = "ResourceARN"
        date = 'CreationTime'
        cfn_type = 'AWS::FSx::FileSystem'
        id_prefix = 'fs-'
        dimension = 'FileSystemId'

    source_mapping = {
        'describe': DescribeFSx
    }


@resources.register('fsx-volume')
class FSxVolume(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'fsx'
        enum_spec = ('describe_volumes', 'Volumes', None)
        name = 'Name'
        id = 'VolumeId'
        arn = 'ResourceARN'
        date = 'CreationTime'
        cfn_type = 'AWS::FSx::Volume'
        filter_name = 'VolumeIds'
        filter_type = 'list'
        default_report_fields = (
            'CreationTime',
            'FileSystemId',
            'Name',
            'VolumeId',
            'VolumeType',
            'Lifecycle',
            'OpenZFSConfiguration.VolumePath'
        )
        universal_taggable = object()
        permissions_augment = ('fsx:ListTagsForResource',)
        id_prefix = 'fsvol-'

    source_mapping = {
        "describe": DescribeWithResourceTags
    }
    permissions = ('fsx:DescribeVolumes', )


@FSx.filter_registry.register('volume')
class FSxVolumesFilter(ListItemFilter):
    schema = type_schema(
        'volume',
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    annotation_key = 'c7n:Volumes'
    permissions = ('fsx:DescribeVolumes', 'fsx:ListTagsForResource')

    def __init__(self, data, manager=None):
        data['key'] = f'"{self.annotation_key}"'
        super().__init__(data, manager)

    def process(self, resources, event=None):
        vol = self.manager.get_resource_manager('aws.fsx-volume')

        # NOTE: each fsx item contains only RootVolumeId and does not contain
        # children volumes ids. So, cannot filter out individual volumes by ids

        volumes = vol.resources()
        mapping = group_by(volumes, 'FileSystemId')

        model = self.manager.get_model()
        for res in resources:
            res[self.annotation_key] = mapping.get(res[model.id], [])
        return super().process(resources, event)


@resources.register('fsx-storage-virtual-machine')
class FSxStorageVirtualMachine(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'fsx'
        enum_spec = ('describe_storage_virtual_machines', 'StorageVirtualMachines', None)
        name = 'Name'
        id = 'StorageVirtualMachineId'
        arn = 'ResourceARN'
        date = 'CreationTime'
        cfn_type = 'AWS::FSx::StorageVirtualMachine'
        filter_name = 'StorageVirtualMachineIds'
        filter_type = 'list'
        id_prefix = 'svm-'
        universal_taggable = object()
        permissions_augment = ('fsx:ListTagsForResource',)
        default_report_fields = (
            'StorageVirtualMachineId',
            'Name',
            'FileSystemId',
            'Lifecycle',
            'Subtype',
        )

    source_mapping = {
        'describe': DescribeWithResourceTags
    }
    permissions = ('fsx:DescribeStorageVirtualMachines',)


@FSxStorageVirtualMachine.filter_registry.register('active-directory')
class SvmActiveDirectoryFilter(ValueFilter):
    """Filter ontap storage virtual machines on the directory they're joined to.

    Unlike fsx for windows, which reports an ActiveDirectoryId that the
    `directory` filter can relate on, an ontap svm reports every join - managed
    or not - through SelfManagedActiveDirectoryConfiguration with no directory
    id. The joined directory is resolved by matching the svm's configured dns
    servers against directory service, and the directory is annotated for
    filtering.

    Replication targets carry no join of their own and svms still settling
    haven't got one yet, so neither is reported on.

    :example:

    .. code-block:: yaml

        policies:
          - name: fsx-ontap-svm-must-use-managed-ad
            resource: aws.fsx-storage-virtual-machine
            filters:
              - or:
                  # an svm that resolves to no directory matches here too
                  - type: active-directory
                    key: Type
                    value: [MicrosoftAD, SharedMicrosoftAD]
                    op: not-in
                  # a misconfigured svm keeps reporting the directory it was
                  # joined to while the join itself is broken
                  - Lifecycle: MISCONFIGURED
    """

    schema = type_schema(
        'active-directory', rinherit=ValueFilter.schema,
        **{'resolve-on': {
            'enum': ['dns-ips', 'same-vpc', 'domain-name'],
            'default': 'dns-ips',
            'description': (
                'Evidence accepted when resolving the join. dns-ips only, the '
                'default, is the sole evidence that establishes which domain '
                'controllers an svm actually uses. same-vpc additionally '
                'accepts a domain name match when the directory sits in the '
                "same vpc as the svm's file system, for estates pointing svms "
                'at a resolver endpoint rather than at the controllers. '
                'domain-name accepts a name match outright, which an on '
                'premises domain of the same name also satisfies.')}})
    schema_alias = False
    annotation_key = 'c7n:ActiveDirectory'
    resolution_key = 'c7n:ActiveDirectoryResolution'

    # replication targets inherit identity from the source rather than
    # joining a directory themselves
    non_ad_subtypes = ('DP_DESTINATION', 'SYNC_DESTINATION', 'SYNC_SOURCE')
    transient_lifecycles = ('CREATING', 'PENDING', 'DELETING')

    def get_permissions(self):
        perms = set(self.directory_manager().get_permissions())
        if self.data.get('resolve-on') == 'same-vpc':
            perms.update(self.manager.get_resource_manager('aws.fsx').get_permissions())
        return sorted(perms)

    def get_file_system_vpcs(self):
        return {f['FileSystemId']: f.get('VpcId') for f in
                self.manager.get_resource_manager('aws.fsx').resources(augment=False)}

    def directory_manager(self):
        return self.manager.get_resource_manager('aws.directory')

    def in_scope(self, svm):
        return (svm.get('Subtype') not in self.non_ad_subtypes and
                svm.get('Lifecycle') not in self.transient_lifecycles)

    def resolve(self, svm, directories, file_system_vpcs=None):
        """Resolve the svm's join to a directory service directory.

        fsx reports the domain name uppercased where directory service doesn't,
        so names only compare case insensitively. A name on its own doesn't
        establish which domain controllers are in use - an on premises domain of
        the same name resolves identically - so only a dns ip match resolves.
        """
        ad = (svm.get('ActiveDirectoryConfiguration') or {}).get(
            'SelfManagedActiveDirectoryConfiguration')
        if not ad:
            return None, {'reason': 'NoActiveDirectory'}

        dns_ips = set(ad.get('DnsIps') or ())
        domain = (ad.get('DomainName') or '').lower().rstrip('.')

        name_only = None
        for d in directories:
            owner = d.get('OwnerDirectoryDescription') or {}
            # a directory shared from another account reports the owning
            # account's domain controllers
            directory_ips = set(d.get('DnsIpAddrs') or ()) | set(owner.get('DnsIpAddrs') or ())
            name_match = bool(domain) and domain == d.get('Name', '').lower().rstrip('.')
            ip_match = bool(dns_ips and dns_ips & directory_ips)
            if ip_match:
                return d, {'reason': 'Resolved',
                           'matched-on': name_match and 'dns-ips,domain-name' or 'dns-ips'}
            if name_match and name_only is None:
                # several directories can carry the same domain name, keep the
                # first so the annotation is stable between runs
                name_only = d

        if name_only is not None:
            resolve_on = self.data.get('resolve-on', 'dns-ips')
            if resolve_on == 'domain-name':
                return name_only, {'reason': 'Resolved', 'matched-on': 'domain-name'}
            if resolve_on == 'same-vpc':
                fs_vpc = (file_system_vpcs or {}).get(svm.get('FileSystemId'))
                directory_vpc = (name_only.get('VpcSettings') or {}).get('VpcId')
                if fs_vpc and directory_vpc and fs_vpc == directory_vpc:
                    return name_only, {'reason': 'Resolved',
                                       'matched-on': 'domain-name,same-vpc'}
            return None, {'reason': 'DomainNameOnlyMatch', 'matched-on': 'domain-name',
                          'DirectoryId': name_only.get('DirectoryId')}
        return None, {'reason': 'UnresolvedDirectory',
                      'DomainName': ad.get('DomainName'), 'DnsIps': sorted(dns_ips)}

    def process(self, resources, event=None):
        directories = self.directory_manager().resources(augment=False)
        file_system_vpcs = (
            self.get_file_system_vpcs()
            if self.data.get('resolve-on') == 'same-vpc' else None)
        results = []
        for r in resources:
            if not self.in_scope(r):
                continue
            directory, resolution = self.resolve(r, directories, file_system_vpcs)
            # an unresolved join annotates no directory, so a policy asking for
            # a directory attribute matches it rather than clearing it
            r[self.annotation_key] = directory or {}
            r[self.resolution_key] = resolution
            if self.match(directory or {}):
                results.append(r)
        return results


@resources.register('fsx-backup')
class FSxBackup(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'fsx'
        enum_spec = ('describe_backups', 'Backups', None)
        name = id = 'BackupId'
        arn = "ResourceARN"
        date = 'CreationTime'


@FSxBackup.action_registry.register('delete')
class DeleteBackup(BaseAction):
    """
    Delete backups

    :example:

    .. code-block:: yaml

        policies:
            - name: delete-backups
              resource: fsx-backup
              filters:
                - type: value
                  value_type: age
                  key: CreationDate
                  value: 30
                  op: gt
              actions:
                - type: delete
    """
    permissions = ('fsx:DeleteBackup',)
    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('fsx')
        for r in resources:
            try:
                client.delete_backup(BackupId=r['BackupId'])
            except client.exceptions.BackupRestoring as e:
                self.log.warning(
                    'Unable to delete backup for: %s - %s - %s' % (
                        r['FileSystemId'], r['BackupId'], e))


FSxBackup.filter_registry.register('marked-for-op', TagActionFilter)

FSx.filter_registry.register('marked-for-op', TagActionFilter)
FSx.filter_registry.register('metrics', MetricsFilter)


@FSxBackup.action_registry.register('mark-for-op')
@FSx.action_registry.register('mark-for-op')
class MarkForOpFileSystem(TagDelayedAction):

    permissions = ('fsx:TagResource',)


@FSxBackup.action_registry.register('tag')
@FSx.action_registry.register('tag')
class TagFileSystem(Tag):
    concurrency = 2
    batch_size = 5
    permissions = ('fsx:TagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.tag_resource(ResourceARN=r['ResourceARN'], Tags=tags)


@FSxBackup.action_registry.register('remove-tag')
@FSx.action_registry.register('remove-tag')
class UnTagFileSystem(RemoveTag):
    concurrency = 2
    batch_size = 5
    permissions = ('fsx:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):
        for r in resources:
            client.untag_resource(ResourceARN=r['ResourceARN'], TagKeys=tag_keys)


@FSx.action_registry.register('update')
class UpdateFileSystem(BaseAction):
    """
    Update FSx resource configurations

    :example:

    .. code-block:: yaml

        policies:
            - name: update-fsx-resource
              resource: fsx
              actions:
                - type: update
                  WindowsConfiguration:
                    AutomaticBackupRetentionDays: 1
                    DailyAutomaticBackupStartTime: '04:30'
                    WeeklyMaintenanceStartTime: '04:30'
                  LustreConfiguration:
                    WeeklyMaintenanceStartTime: '04:30'

    Reference: https://docs.aws.amazon.com/fsx/latest/APIReference/API_UpdateFileSystem.html
    """
    permissions = ('fsx:UpdateFileSystem',)

    schema = type_schema(
        'update',
        WindowsConfiguration={'type': 'object'},
        LustreConfiguration={'type': 'object'}
    )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('fsx')
        for r in resources:
            client.update_file_system(
                FileSystemId=r['FileSystemId'],
                WindowsConfiguration=self.data.get('WindowsConfiguration', {}),
                LustreConfiguration=self.data.get('LustreConfiguration', {})
            )


@FSx.action_registry.register('backup')
class BackupFileSystem(BaseAction):
    """
    Create Backups of File Systems

    Tags are specified in key value pairs, e.g.: BackupSource: CloudCustodian

    :example:

    .. code-block:: yaml

        policies:
            - name: backup-fsx-resource
              comment: |
                  creates a backup of fsx resources and
                  copies tags from file system to the backup
              resource: fsx
              actions:
                - type: backup
                  copy-tags: True
                  tags:
                    BackupSource: CloudCustodian

            - name: backup-fsx-resource-copy-specific-tags
              comment: |
                  creates a backup of fsx resources and
                  copies tags from file system to the backup
              resource: fsx
              actions:
                - type: backup
                  copy-tags:
                    - Application
                    - Owner
                    # or use '*' to specify all tags
                  tags:
                    BackupSource: CloudCustodian
    """

    permissions = ('fsx:CreateBackup',)

    schema = type_schema(
        'backup',
        **{
            'tags': {
                'type': 'object'
            },
            'copy-tags': {
                'oneOf': [
                    {
                        'type': 'boolean'
                    },
                    {
                        'type': 'array',
                        'items': {
                            'type': 'string'
                        }
                    }
                ]
            }
        }
    )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('fsx')
        user_tags = self.data.get('tags', {})
        copy_tags = self.data.get('copy-tags', True)
        for r in resources:
            tags = coalesce_copy_user_tags(r, copy_tags, user_tags)
            try:
                if tags:
                    client.create_backup(
                        FileSystemId=r['FileSystemId'],
                        Tags=tags
                    )
                else:
                    client.create_backup(
                        FileSystemId=r['FileSystemId']
                    )
            except client.exceptions.BackupInProgress as e:
                self.log.warning(
                    'Unable to create backup for: %s - %s' % (r['FileSystemId'], e))


@FSx.action_registry.register('delete')
class DeleteFileSystem(BaseAction):
    """
    Delete Filesystems

    If `force` is set to True, this action will attempt to delete all
    dependencies necessary to delete the file system.

    You can override the default retry settings for deletion by specifying
    `retry-delay` (default: 1 seconds, if force is True defaults to 30 seconds)
    and `retry-max-attempts` (default: 1, if force is True defaults to 10).
    Adjust the retry settings, as necessary when using `force` set to `True`.
    FSx for Ontap takes extra time to delete all volumes before it can delete
    the file system. OpenZFS also takes extra time to delete S3 access points.

    Note:

    - If `skip-snapshot` is set to True, no final snapshot will be created.
    - FSx for OnTap resources do not create snapshot backups on deletion even \
      if skip-snapshot is set to False.
    - FSx for Lustre resources using the Scratch deployment type do not support \
      final backups on deletion. Set `force` to True to delete these when \
      `skip-snapshot` is set to False.

    Annotated Permissions:

    - fsx:DeleteFileSystem (required)
    - fsx:CreateBackup (if skip-snapshot is False or not set)
    - fsx:DescribeStorageVirtualMachines (if force is True for ONTAP)
    - fsx:DeleteStorageVirtualMachine (if force is True for ONTAP)
    - fsx:DescribeVolumes (if force is True for ONTAP and OpenZFS)
    - fsx:DeleteVolume (if force is True for ONTAP and OpenZFS)
    - fsx:DescribeS3AccessPointAttachments (if force is True for OpenZFS)
    - fsx:DetachAndDeleteS3AccessPoint (if force is True for OpenZFS)
    - s3:DeleteAccessPoint (if force is True for OpenZFS)

    :example:

    .. code-block:: yaml

        policies:
            - name: delete-fsx-instance-with-snapshot
              resource: fsx
              filters:
                - FileSystemId: fs-1234567890123
              actions:
                - type: delete
                  copy-tags:
                    - Application
                    - Owner
                  tags:
                    DeletedBy: CloudCustodian

            - name: delete-fsx-instance-skip-snapshot
              resource: fsx
              filters:
                - FileSystemId: fs-1234567890123
              actions:
                - type: delete
                  force: True
                  retry-delay: 30
                  retry-max-attempts: 10
                  skip-snapshot: True

    """

    permissions = ('fsx:DeleteFileSystem',
                   'fsx:CreateBackup',
                   'fsx:DescribeStorageVirtualMachines',
                   'fsx:DeleteStorageVirtualMachine',
                   'fsx:DescribeVolumes',
                   'fsx:DeleteVolume',
                   'fsx:DescribeS3AccessPointAttachments',
                   'fsx:DetachAndDeleteS3AccessPoint',
                   's3:DeleteAccessPoint',)

    schema = type_schema(
        'delete',
        **{
            'force': {'type': 'boolean'},
            'retry-delay': {'type': 'number', 'minimum': 1},
            'retry-max-attempts': {'type': 'number', 'minimum': 1},
            'skip-snapshot': {'type': 'boolean'},
            'tags': {'type': 'object'},
            'copy-tags': {
                'oneOf': [
                    {
                        'type': 'array',
                        'items': {
                            'type': 'string'
                        }
                    },
                    {
                        'type': 'boolean'
                    }
                ]
            }
        }
    )

    # ONTAP does not currently have its own configuration block in boto3.
    FSTYPE_CONFIG_KEY = {
        'WINDOWS': 'WindowsConfiguration',
        'LUSTRE': 'LustreConfiguration',
        'OPENZFS': 'OpenZFSConfiguration',
    }

    def _lustre_get_delete_config(self, config, resource):
        """
        Get delete configuration specific to LUSTRE filesystems.
        """
        if self.data.get("skip-snapshot", False):
            return config

        deployment_type = resource.get("LustreConfiguration", {}).get("DeploymentType")

        # There is no final backup support for SCRATCH deployment
        # types. Override to skip final backup and final backup tags
        # when we are forcing deletion.
        if deployment_type == "SCRATCH_2" or deployment_type == "SCRATCH_1":
            self.log.warning(
                'Final backup not supported for SCRATCH deployment '
                'types (set Force to True to delete): %s' % (resource['FileSystemId'])
            )
            if self.data.get('force'):
                del config['FinalBackupTags']
                del config['SkipFinalBackup']
        return config

    def _openzfs_get_delete_config(self, config, _):
        """
        Get delete configuration specific to OPENZFS filesystems.
        """
        # OpenZFS requires this option to delete all child volumes and snapshots
        if self.data.get('force'):
            config['Options'] = ['DELETE_CHILD_VOLUMES_AND_SNAPSHOTS']
        return config

    def _ontap_delete_dependencies(self, client, resource, retry):
        """
        Delete dependent resources for an ONTAP file system.
        """
        svms = client.describe_storage_virtual_machines(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': [resource['FileSystemId']],
                }
            ]
        ).get('StorageVirtualMachines', [])

        for svm in svms:
            if svm.get('Lifecycle') == 'DELETING':
                continue
            try:
                retry(
                    client.delete_storage_virtual_machine,
                    StorageVirtualMachineId=svm['StorageVirtualMachineId'],
                )
            except Exception as e:
                self.log.error(
                    'Unable to delete SVM for: %s - %s - %s'
                    % (resource['FileSystemId'], svm['StorageVirtualMachineId'], e)
                )

        volumes = client.describe_volumes(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': [resource['FileSystemId']],
                }
            ]
        ).get('Volumes', [])

        for volume in volumes:
            if volume.get('Lifecycle') == 'DELETING':
                continue
            try:
                retry(client.delete_volume, VolumeId=volume['VolumeId'])
            except Exception as e:
                self.log.error(
                    'Unable to delete volume for: %s - %s - %s'
                    % (resource['FileSystemId'], volume['VolumeId'], e)
                )

    def _openzfs_delete_dependencies(self, client, resource, retry):
        """
        Delete dependent resources for an OPENZFS file system.
        """
        s3_attachments = client.describe_s3_access_point_attachments(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': [resource['FileSystemId']],
                }
            ]
        ).get('S3AccessPointAttachments', [])

        for s3_attachment in s3_attachments:
            if s3_attachment.get('Lifecycle') == 'DELETING':
                continue
            try:
                retry(client.detach_and_delete_s3_access_point, Name=s3_attachment['Name'])
            except Exception as e:
                self.log.error(
                    'Unable to delete S3 Access Point for: %s - %s - %s -%s'
                    % (
                        resource['FileSystemId'],
                        s3_attachment['Name'],
                        s3_attachment['S3AccessPointArn'],
                        e,
                    )
                )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('fsx')

        skip_snapshot = self.data.get('skip-snapshot', False)
        copy_tags = self.data.get('copy-tags', True)
        user_tags = self.data.get('tags', [])

        if self.data.get('force'):
            # Override default retry settings when force is True
            if not self.data.get('retry-delay'):
                self.data['retry-delay'] = 30
            if not self.data.get('retry-max-attempts'):
                self.data['retry-max-attempts'] = 10

        retry_delay = self.data.get('retry-delay', 1)
        retry_max_attempts = self.data.get('retry-max-attempts', 1)
        retry = get_retry(
            retry_codes=('BadRequest'),
            min_delay=retry_delay,
            max_attempts=retry_max_attempts,
            log_retries=True,
        )

        # Deletion parameters and dependency cleanup behavior vary
        # by filesystem type
        fstype_ops = {
            'get_delete_config': {
                'LUSTRE': self._lustre_get_delete_config,
                'OPENZFS': self._openzfs_get_delete_config,
            },
            'delete_dependencies': {
                'ONTAP': self._ontap_delete_dependencies,
                'OPENZFS': self._openzfs_delete_dependencies,
            },
        }

        for r in resources:
            tags = coalesce_copy_user_tags(r, copy_tags, user_tags)
            config = {'SkipFinalBackup': skip_snapshot}
            if tags and not skip_snapshot:
                config['FinalBackupTags'] = tags

            delete_args = {
                'FileSystemId': r['FileSystemId'],
            }

            fs_type = r.get('FileSystemType')
            if callable(get_delete_config := fstype_ops['get_delete_config'].get(fs_type)):
                config = get_delete_config(config, r)

            if config_key := self.FSTYPE_CONFIG_KEY.get(fs_type):
                delete_args[config_key] = config

            if self.data.get('force') and callable(
                delete_dependencies := fstype_ops['delete_dependencies'].get(fs_type)
            ):
                delete_dependencies(client, r, retry)

            try:
                retry(
                    client.delete_file_system,
                    **delete_args,
                )

            except Exception as e:
                self.log.error('Unable to delete: %s - %s' % (r['FileSystemId'], e))
                raise e


@FSx.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


@FSxBackup.filter_registry.register('kms-key')
class KmsFilterFsxBackup(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


@FSx.filter_registry.register('consecutive-backups')
class ConsecutiveBackups(Filter):
    """Returns consecutive daily FSx backups, which are equal to/or greater than n days.
    :Example:

    .. code-block:: yaml

            policies:
              - name: fsx-daily-backup-count
                resource: fsx
                filters:
                  - type: consecutive-backups
                    days: 5
                actions:
                  - notify
    """
    schema = type_schema('consecutive-backups',
                         days={'type': 'number', 'minimum': 1},
                         required=['days'])
    permissions = ('fsx:DescribeBackups', 'fsx:DescribeVolumes',)
    annotation = 'c7n:FSxBackups'

    def describe_backups(self, client, name=None, filters=[]):
        desc_backups = []
        try:
            paginator = client.get_paginator('describe_backups')
            paginator.PAGE_ITERATOR_CLS = RetryPageIterator
            desc_backups = paginator.paginate(Filters=[
                {
                    'Name': name,
                    'Values': filters,
                }]).build_full_result().get('Backups', [])
        except Exception as err:
            self.log.warning(
                'Unable to describe backups for ids: %s - %s' % (filters, err))
        return desc_backups

    def ontap_process_resource_set(self, client, resources):
        ontap_fid_backups = {}
        ontap_backups = []
        ontap_fids = [r['FileSystemId'] for r in resources]
        if ontap_fids:
            ontap_volumes = client.describe_volumes(Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': ontap_fids,
                }])
            ontap_vids = [v['VolumeId'] for v in ontap_volumes['Volumes']]
            for ovid in chunks(ontap_vids, 20):
                ontap_backups = self.describe_backups(client, 'volume-id', ovid)
            if ontap_backups:
                for ontap in ontap_backups:
                    ontap_fid_backups.setdefault(ontap['Volume']
                                           ['FileSystemId'], []).append(ontap)
        for r in resources:
            r[self.annotation] = ontap_fid_backups.get(r['FileSystemId'], [])

    def nonontap_process_resource_set(self, client, resources):
        fid_backups = {}
        nonontap_backups = []
        nonontap_fids = [r['FileSystemId'] for r in resources]
        if nonontap_fids:
            for nonontap_fid in chunks(nonontap_fids, 20):
                nonontap_backups = self.describe_backups(client, 'file-system-id', nonontap_fid)
            if nonontap_backups:
                for nonontap in nonontap_backups:
                    fid_backups.setdefault(nonontap['FileSystem']
                                           ['FileSystemId'], []).append(nonontap)
        for r in resources:
            r[self.annotation] = fid_backups.get(r['FileSystemId'], [])

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('fsx')
        results = []
        ontap_resource_set, nonontap_resource_set = [], []
        retention = self.data.get('days')
        utcnow = datetime.utcnow()
        expected_dates = set()
        for days in range(1, retention + 1):
            expected_dates.add((utcnow - timedelta(days=days)).strftime('%Y-%m-%d'))

        for r in resources:
            if self.annotation not in r:
                if r['FileSystemType'] == 'ONTAP':
                    ontap_resource_set.append(r)
                else:
                    nonontap_resource_set.append(r)

        if ontap_resource_set:
            self.ontap_process_resource_set(client, ontap_resource_set)
        if nonontap_resource_set:
            self.nonontap_process_resource_set(client, nonontap_resource_set)

        for r in resources:
            backup_dates = set()
            for backup in r[self.annotation]:
                if backup['Lifecycle'] == 'AVAILABLE':
                    backup_dates.add(backup['CreationTime'].strftime('%Y-%m-%d'))
            if expected_dates.issubset(backup_dates):
                results.append(r)
        return results


@FSx.filter_registry.register('subnet')
class Subnet(SubnetFilter):

    RelatedIdsExpression = 'SubnetIds[]'


@FSx.filter_registry.register('vpc')
class VpcFilter(VpcFilter):

    RelatedIdsExpression = "VpcId"


@FSx.filter_registry.register('security-group')
class FSxSecurityGroupFilter(SecurityGroupFilter):
    """Filter fsx file systems by their attached security groups.

    describe_file_systems does not report security groups; they are attached
    to the file system's elastic network interfaces, so they're resolved via
    the file system's NetworkInterfaceIds.

    :example:

    .. code-block:: yaml

        policies:
          - name: fsx-public-security-group
            resource: aws.fsx
            filters:
              - type: security-group
                key: GroupName
                value: default
    """

    RelatedIdsExpression = ""
    eni_group_cache = None

    def get_permissions(self):
        return tuple(super().get_permissions()) + ('ec2:DescribeNetworkInterfaces',)

    def _describe_eni_groups(self, eni_ids):
        client = local_session(self.manager.session_factory).client('ec2')
        groups = {}
        for eni_set in chunks(sorted(eni_ids), 50):
            try:
                enis = client.describe_network_interfaces(
                    NetworkInterfaceIds=eni_set)['NetworkInterfaces']
            except client.exceptions.ClientError as e:
                if e.response['Error']['Code'] != 'InvalidNetworkInterfaceID.NotFound':
                    raise
                # a file system being deleted can reference a departed eni,
                # fall back to individual lookups so one stale id doesn't
                # discard the whole batch.
                enis = []
                for eni_id in eni_set:
                    try:
                        enis.extend(client.describe_network_interfaces(
                            NetworkInterfaceIds=[eni_id])['NetworkInterfaces'])
                    except client.exceptions.ClientError as e:
                        if e.response['Error']['Code'] != 'InvalidNetworkInterfaceID.NotFound':
                            raise
                        self.log.warning(
                            'fsx security-group filter, eni:%s not found', eni_id)
            for eni in enis:
                groups[eni['NetworkInterfaceId']] = [
                    g['GroupId'] for g in eni.get('Groups', ())]
        return groups

    def get_related_ids(self, resources):
        if self.eni_group_cache is None:
            eni_ids = set()
            for r in resources:
                eni_ids.update(r.get('NetworkInterfaceIds', ()))
            self.eni_group_cache = (
                self._describe_eni_groups(eni_ids) if eni_ids else {})

        group_ids = set()
        for r in resources:
            for eni_id in r.get('NetworkInterfaceIds', ()):
                group_ids.update(self.eni_group_cache.get(eni_id, ()))
        return list(group_ids)


FSx.filter_registry.register('network-location', NetworkLocation)


@FSx.filter_registry.register('directory')
class FSxDirectoryFilter(RelatedResourceFilter):
    """Filter fsx for windows file systems by the directory they're joined to.

    ActiveDirectoryId is only reported for an aws managed microsoft ad, and a
    self managed join reports none at all.

    Note an id outlives the directory it names. A related resource that can't
    be resolved is only treated as a match for `value: absent`, so a policy
    that asks about a directory attribute has to ask for the missing directory
    separately, or an id left behind by a deleted directory goes unreported.

    :example:

    .. code-block:: yaml

        policies:
          - name: fsx-windows-must-use-managed-ad
            resource: aws.fsx
            filters:
              - FileSystemType: WINDOWS
              - or:
                  # no directory, or one that no longer exists
                  - type: directory
                    key: DirectoryId
                    value: absent
                  - type: directory
                    key: Type
                    value: [MicrosoftAD, SharedMicrosoftAD]
                    op: not-in
                  # a windows file system unavailable for a change to its
                  # active directory configuration still names the directory
                  - Lifecycle: MISCONFIGURED_UNAVAILABLE
    """

    schema = type_schema(
        'directory', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    schema_alias = False

    RelatedResource = "c7n.resources.directory.Directory"
    RelatedIdsExpression = "WindowsConfiguration.ActiveDirectoryId"
    AnnotationKey = "matched-directories"


@FSx.filter_registry.register('svm')
class FSxStorageVirtualMachineFilter(ListItemFilter):
    """Filter fsx file systems by their storage virtual machines.

    ontap configures active directory per storage virtual machine, so a file
    system with no svm is joined to nothing at all.

    :example:

    .. code-block:: yaml

        policies:
          - name: fsx-ontap-without-storage-virtual-machine
            resource: aws.fsx
            filters:
              - FileSystemType: ONTAP
              - Lifecycle: AVAILABLE
              - type: svm
                count: 0
    """

    schema = type_schema(
        'svm',
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    annotation_key = 'c7n:StorageVirtualMachines'
    permissions = ('fsx:DescribeStorageVirtualMachines', 'fsx:ListTagsForResource')

    def __init__(self, data, manager=None):
        data['key'] = f'"{self.annotation_key}"'
        super().__init__(data, manager)

    def process(self, resources, event=None):
        svms = self.manager.get_resource_manager(
            'aws.fsx-storage-virtual-machine').resources()
        mapping = group_by(svms, 'FileSystemId')
        model = self.manager.get_model()
        for res in resources:
            res[self.annotation_key] = mapping.get(res[model.id], [])
        return super().process(resources, event)


FSx.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)
