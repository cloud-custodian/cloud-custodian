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
from c7n.filters import Filter, ListItemFilter, MetricsFilter
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
        default_report_fields = (
            'StorageVirtualMachineId',
            'Name',
            'FileSystemId',
            'Lifecycle',
            'Subtype',
        )
    permissions = ('fsx:DescribeStorageVirtualMachines',)


MANAGED_DIRECTORY_TYPES = ('MicrosoftAD', 'SharedMicrosoftAD')

# replication targets participate in no ad join of their own, they inherit
# identity from the source, so they aren't in scope for an ad control.
NON_AD_SVM_SUBTYPES = ('DP_DESTINATION', 'SYNC_DESTINATION', 'SYNC_SOURCE')

# an svm or file system still settling hasn't got its directory yet
TRANSIENT_SVM_LIFECYCLES = ('CREATING', 'PENDING', 'DELETING')
TRANSIENT_FS_LIFECYCLES = ('CREATING', 'DELETING')

# a misconfigured resource keeps reporting the directory it was joined to
# while the join itself is broken, most often expired credentials or domain
# controllers it can no longer reach. reporting that as joined would clear a
# resource that isn't actually using the directory.
BROKEN_AD_SVM_LIFECYCLES = ('MISCONFIGURED',)
BROKEN_AD_FS_LIFECYCLES = ('MISCONFIGURED', 'MISCONFIGURED_UNAVAILABLE')


def describe_directories(manager):
    client = local_session(manager.session_factory).client('ds')
    directories = []
    for page in client.get_paginator('describe_directories').paginate():
        directories.extend(page['DirectoryDescriptions'])
    return directories


def resolve_ad_config(ad, directories):
    """Resolve a self managed ad config block to a directory service directory.

    fsx reports the domain name uppercased where directory service doesn't, so
    names only compare case insensitively. A name on its own doesn't establish
    which domain controllers are actually in use - an on premises domain of the
    same name resolves identically - so only a dns ip match can clear a
    resource.
    """
    dns_ips = set(ad.get('DnsIps') or ())
    domain = (ad.get('DomainName') or '').lower().rstrip('.')

    name_only = None
    for d in directories:
        owner = d.get('OwnerDirectoryDescription') or {}
        directory_ips = set(d.get('DnsIpAddrs') or ()) | set(owner.get('DnsIpAddrs') or ())
        name_match = bool(domain) and domain == d.get('Name', '').lower().rstrip('.')
        ip_match = bool(dns_ips and dns_ips & directory_ips)
        if not (ip_match or name_match):
            continue
        found = {'DirectoryId': d.get('DirectoryId'),
                 'DirectoryType': d.get('Type'),
                 'DirectoryName': d.get('Name'),
                 'matched-on': (ip_match and name_match and 'dns-ips,domain-name' or
                                ip_match and 'dns-ips' or 'domain-name')}
        if not ip_match:
            # several directories can carry the same domain name, keep the
            # first so the annotation is stable rather than whichever the
            # api happened to return last.
            if name_only is None:
                name_only = dict(found, managed=False, reason='DomainNameOnlyMatch')
            continue
        found['managed'] = d.get('Type') in MANAGED_DIRECTORY_TYPES
        found['reason'] = (
            'ManagedDirectory' if found['managed'] else 'UnmanagedDirectory')
        return found

    if name_only:
        return name_only
    return {'managed': False, 'reason': 'UnresolvedDirectory',
            'DomainName': ad.get('DomainName'), 'DnsIps': sorted(dns_ips)}


def resolve_svm(svm, directories):
    """Resolve an ontap svm's directory, `managed` is None when out of scope."""
    if svm.get('Subtype') in NON_AD_SVM_SUBTYPES:
        return {'managed': None, 'reason': 'SubtypeNotAdJoined',
                'Subtype': svm.get('Subtype')}
    if svm.get('Lifecycle') in TRANSIENT_SVM_LIFECYCLES:
        return {'managed': None, 'reason': 'TransientLifecycle',
                'Lifecycle': svm.get('Lifecycle')}
    if svm.get('Lifecycle') in BROKEN_AD_SVM_LIFECYCLES:
        return {'managed': False, 'reason': 'MisconfiguredDirectoryJoin',
                'Lifecycle': svm.get('Lifecycle'),
                'LifecycleTransitionReason': (
                    svm.get('LifecycleTransitionReason') or {}).get('Message')}
    ad = (svm.get('ActiveDirectoryConfiguration') or {}).get(
        'SelfManagedActiveDirectoryConfiguration')
    if not ad:
        return {'managed': False, 'reason': 'NoActiveDirectory'}
    return resolve_ad_config(ad, directories)


def resolve_windows(fs, directories):
    """Resolve an fsx for windows file system's directory.

    Windows reports an ActiveDirectoryId for a managed directory, but that id
    outliving the directory it names would otherwise read as compliant, so it's
    resolved rather than trusted.
    """
    config = fs.get('WindowsConfiguration') or {}
    directory_id = config.get('ActiveDirectoryId')
    if directory_id:
        for d in directories:
            if d.get('DirectoryId') != directory_id:
                continue
            managed = d.get('Type') in MANAGED_DIRECTORY_TYPES
            return {'managed': managed,
                    'reason': 'ManagedDirectory' if managed else 'UnmanagedDirectory',
                    'DirectoryId': directory_id,
                    'DirectoryType': d.get('Type'),
                    'DirectoryName': d.get('Name'),
                    'matched-on': 'directory-id'}
        return {'managed': False, 'reason': 'DirectoryNotFound',
                'DirectoryId': directory_id}
    if config.get('SelfManagedActiveDirectoryConfiguration'):
        return resolve_ad_config(
            config['SelfManagedActiveDirectoryConfiguration'], directories)
    return {'managed': False, 'reason': 'NoActiveDirectory'}


class ActiveDirectoryFilterBase(Filter):

    schema_alias = False
    annotation_key = 'c7n:ActiveDirectory'

    def match_found(self, found):
        match = self.data.get('match', 'not-managed')
        if match == 'any':
            return True
        # `managed` is None for resources an ad join doesn't apply to, which
        # are neither compliant nor in violation.
        if found['managed'] is None:
            return False
        return found['managed'] is (match == 'managed')


@FSxStorageVirtualMachine.filter_registry.register('active-directory')
class SvmActiveDirectoryFilter(ActiveDirectoryFilterBase):
    """Filter ontap storage virtual machines on the directory they're joined to.

    Unlike fsx for windows, which reports an ActiveDirectoryId for a managed
    directory, an ontap svm reports every join - managed or not - through
    SelfManagedActiveDirectoryConfiguration with no directory id. The joined
    directory is resolved by matching the svm's configured dns servers against
    directory service.

    `match: not-managed` fails closed, an svm is only cleared when it can be
    positively resolved to an aws managed microsoft ad.

    Note the same violation is reported by the file system level filter of the
    same name, which names the offending svms in its annotation. Running both
    against one account reports each violation twice, once per resource type.

    :example:

    .. code-block:: yaml

        policies:
          - name: fsx-ontap-svm-must-use-managed-ad
            resource: aws.fsx-storage-virtual-machine
            filters:
              - type: active-directory
                match: not-managed
    """

    schema = type_schema(
        'active-directory',
        match={'enum': ['managed', 'not-managed', 'any']})
    permissions = ('ds:DescribeDirectories',)

    def process(self, resources, event=None):
        directories = describe_directories(self.manager)
        results = []
        for r in resources:
            found = resolve_svm(r, directories)
            r[self.annotation_key] = found
            if self.match_found(found):
                results.append(r)
        return results


@FSx.filter_registry.register('active-directory')
class FSxActiveDirectoryFilter(ActiveDirectoryFilterBase):
    """Filter fsx file systems on the directory they're joined to.

    Windows file systems are assessed directly. Ontap configures active
    directory per storage virtual machine, so an ontap file system is assessed
    through its svms - one that has no svm at all is joined to nothing, and
    would otherwise go unreported by an svm level policy having no svm to
    report on.

    This covers both file system types, and names the offending svms in its
    annotation, so it doesn't need pairing with the storage virtual machine
    filter of the same name - running both reports each violation twice.

    :example:

    .. code-block:: yaml

        policies:
          - name: fsx-must-use-managed-ad
            resource: aws.fsx
            filters:
              - type: active-directory
                match: not-managed
    """

    schema = type_schema(
        'active-directory',
        match={'enum': ['managed', 'not-managed', 'any']})
    permissions = ('ds:DescribeDirectories', 'fsx:DescribeStorageVirtualMachines')

    def get_svms(self):
        svms = self.manager.get_resource_manager(
            'aws.fsx-storage-virtual-machine').resources()
        return group_by(svms, 'FileSystemId')

    def resolve_ontap(self, fs, svms, directories):
        if not svms:
            return {'managed': False, 'reason': 'NoStorageVirtualMachines'}
        evaluated = []
        for svm in svms:
            found = resolve_svm(svm, directories)
            found['StorageVirtualMachineId'] = svm['StorageVirtualMachineId']
            evaluated.append(found)
        in_scope = [e for e in evaluated if e['managed'] is not None]
        if not in_scope:
            return {'managed': None, 'reason': 'NoAdJoinedStorageVirtualMachines',
                    'storage-virtual-machines': evaluated}
        violations = [e for e in in_scope if not e['managed']]
        if violations:
            return {'managed': False, 'reason': 'StorageVirtualMachineNotManaged',
                    'storage-virtual-machines': violations}
        return {'managed': True, 'reason': 'ManagedDirectory',
                'storage-virtual-machines': in_scope}

    def process(self, resources, event=None):
        directories = describe_directories(self.manager)
        svms = {}
        if any(r.get('FileSystemType') == 'ONTAP' for r in resources):
            svms = self.get_svms()

        results = []
        for r in resources:
            fs_type = r.get('FileSystemType')
            if r.get('Lifecycle') in TRANSIENT_FS_LIFECYCLES:
                found = {'managed': None, 'reason': 'TransientLifecycle',
                         'Lifecycle': r.get('Lifecycle')}
            elif (r.get('Lifecycle') in BROKEN_AD_FS_LIFECYCLES and
                    fs_type in ('WINDOWS', 'ONTAP')):
                found = {'managed': False, 'reason': 'MisconfiguredDirectoryJoin',
                         'Lifecycle': r.get('Lifecycle'),
                         'FailureDetails': (
                             r.get('FailureDetails') or {}).get('Message')}
            elif fs_type == 'WINDOWS':
                found = resolve_windows(r, directories)
            elif fs_type == 'ONTAP':
                found = self.resolve_ontap(
                    r, svms.get(r['FileSystemId'], []), directories)
            else:
                # lustre and openzfs have no active directory integration
                found = {'managed': None, 'reason': 'FileSystemTypeNotAdCapable',
                         'FileSystemType': fs_type}
            r[self.annotation_key] = found
            if self.match_found(found):
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
                eni_ids and self._describe_eni_groups(eni_ids) or {})

        group_ids = set()
        for r in resources:
            for eni_id in r.get('NetworkInterfaceIds', ()):
                group_ids.update(self.eni_group_cache.get(eni_id, ()))
        return list(group_ids)


@FSx.filter_registry.register('network-location')
class FSxNetworkLocation(NetworkLocation):
    """Compare fsx file system, subnet, and security group attributes.

    Security groups are resolved off the file system's network interfaces,
    which needs an additional permission over the base filter.

    :example:

    .. code-block:: yaml

        policies:
          - name: fsx-sg-tag-mismatch
            resource: aws.fsx
            filters:
              - type: network-location
                compare: ["resource", "security-group"]
                key: "tag:Env"
    """

    schema_alias = False

    def get_permissions(self):
        return tuple(super().get_permissions()) + ('ec2:DescribeNetworkInterfaces',)


FSx.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)
