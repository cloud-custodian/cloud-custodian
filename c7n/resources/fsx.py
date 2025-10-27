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
from c7n.filters.vpc import SubnetFilter, VpcFilter
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

    :example:

    .. code-block:: yaml
        If `force` is set to True, this action will attempt to delete all
        dependencies necessary to delete the file system.

        You can override the default retry settings for deletion by specifying
        `retry-delay` (default: 5 seconds) and
        `retry-max-attempts` (default: 2).
        FSx for Ontap may take longer to delete all volumes before it can delete
        the file system.

        Note:
        If `skip-snapshot` is set to True, no final snapshot will be created.
        FSx for OnTap resources do not create snapshot backups on deletion
        even if skip-snapshot is set to True.
        FSx for Lustre resources using the Scratch deployment type do not
        support final backups on deletion.

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

    permissions = ('fsx:DeleteFileSystem', 'fsx:DescribeVolumes')

    schema = type_schema(
        'delete',
        **{
            'force': {'type': 'boolean'},
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

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('fsx')

        skip_snapshot = self.data.get('skip-snapshot', False)
        copy_tags = self.data.get('copy-tags', True)
        user_tags = self.data.get('tags', [])
        retry_delay = self.data.get('retry-delay', 5)
        retry_max_attempts = self.data.get('retry-max-attempts', 2)
        retry = get_retry(retry_codes=('BadRequest'), min_delay=retry_delay,
                    max_attempts=retry_max_attempts, log_retries=True)

        for r in resources:
            tags = coalesce_copy_user_tags(r, copy_tags, user_tags)
            config = {'SkipFinalBackup': skip_snapshot}
            if tags and not skip_snapshot:
                config['FinalBackupTags'] = tags

            delete_args = {
                'FileSystemId': r['FileSystemId'],
            }
            # Determine the correct configuration key based on FileSystemType
            # fs_type == 'ONTAP' does not have its own config in boto3
            fs_type = r.get('FileSystemType')
            config_key = None
            if fs_type == 'WINDOWS':
                config_key = 'WindowsConfiguration'

            elif fs_type == 'LUSTRE':
                config_key = 'LustreConfiguration'

                if self.data.get('force') and not skip_snapshot:
                    deployment_type = r.get("LustreConfiguration", {}).get("DeploymentType")

                    # There is no final backup support for SCRATCH deployment
                    # types. Override to skip final backup and final backup tags
                    # when we are forcing deletion.
                    if deployment_type == "SCRATCH_2" or deployment_type == "SCRATCH_1":
                        self.log.warning(
                            'Force Deletion: Final backup not supported for '
                            'SCRATCH deployment types: %s' % (r['FileSystemId'])
                        )
                        del config['FinalBackupTags']
                        del config['SkipFinalBackup']

            elif fs_type == 'OPENZFS':
                config_key = 'OpenZFSConfiguration'
                # OpenZFS requires this option to delete all child volumes and snapshots
                if self.data.get('force'):
                    config['Options'] = ['DELETE_CHILD_VOLUMES_AND_SNAPSHOTS']

            if self.data.get('force'):
                self._delete_dependencies(client, r, fs_type, retry)

            if config_key and config:
                delete_args[config_key] = config
            try:
                retry(
                    client.delete_file_system,
                    **delete_args,
                )

            except Exception as e:
                self.log.warning('Unable to delete: %s - %s' % (r['FileSystemId'], e))

    def _delete_dependencies(self, client, resource, fs_type, retry):
        """
        Delete dependent resources for a file system.
        """
        additional_permissions = []
        if fs_type == 'ONTAP':
            additional_permissions.append('fsx:DescribeStorageVirtualMachines')
            svms = client.describe_storage_virtual_machines(Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': [resource['FileSystemId']],
                }]).get('StorageVirtualMachines', [])
            if svms:
                additional_permissions.append('fsx:DeleteStorageVirtualMachine')
            for svm in svms:
                if svm.get('Lifecycle') == 'DELETING':
                    continue
                try:
                    retry(
                        client.delete_storage_virtual_machine,
                        StorageVirtualMachineId=svm['StorageVirtualMachineId']
                    )
                except client.exceptions.StorageVirtualMachineNotFound:
                    continue
                except Exception as e:
                    self.log.warning(
                        'Unable to delete SVM for: %s - %s - %s' % (
                            resource['FileSystemId'], svm['StorageVirtualMachineId'], e))

            additional_permissions.append('fsx:DescribeVolumes')
            volumes = client.describe_volumes(Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': [resource['FileSystemId']],
                }]).get('Volumes', [])
            if volumes:
                additional_permissions.append('fsx:DeleteVolume')
            for volume in volumes:
                if volume.get('Lifecycle') == 'DELETING':
                    continue
                try:
                    retry(
                        client.delete_volume,
                        VolumeId=volume['VolumeId']
                    )
                except client.exceptions.VolumeNotFound:
                    continue
                except Exception as e:
                    self.log.warning(
                        'Unable to delete volume for: %s - %s - %s' % (
                            resource['FileSystemId'], volume['VolumeId'], e))
        elif fs_type == 'OPENZFS':
            additional_permissions.append('fsx:DescribeS3AccessPointAttachments')

            s3_attachments = client.describe_s3_access_point_attachments(Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': [resource['FileSystemId']],
                }]).get('S3AccessPointAttachments', [])

            if s3_attachments:
                additional_permissions.extend(['fsx:DetachAndDeleteS3AccessPoint',
                                              's3:DeleteAccessPoint'])

            for s3_attachment in s3_attachments:
                if s3_attachment.get('Lifecycle') == 'DELETING':
                    continue
                try:
                    retry(
                        client.detach_and_delete_s3_access_point,
                        Name=s3_attachment['Name']
                    )
                except client.exceptions.S3AccessPointNotFound:
                    continue
                except Exception as e:
                    self.log.warning(
                        'Unable to delete S3 Access Point for: %s - %s - %s -%s' % (
                            resource['FileSystemId'],
                            s3_attachment['Name'],
                            s3_attachment['S3AccessPointArn'], e
                        )
                    )

        if additional_permissions:
            self.permissions += tuple(additional_permissions)


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


FSx.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)
