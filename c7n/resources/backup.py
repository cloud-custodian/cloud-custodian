# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.filters.kms import KmsRelatedFilter
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.tags import universal_augment
from c7n.utils import local_session


class DescribeBackup(DescribeSource):

    def augment(self, resources):
        resources = super(DescribeBackup, self).augment(resources)
        client = local_session(self.manager.session_factory).client('backup')
        results = []
        for r in resources:
            plan = r.pop('BackupPlan', {})
            r.update(plan)
            try:
                tags = client.list_tags(ResourceArn=r['BackupPlanArn']).get('Tags', {})
            except client.exceptions.ResourceNotFoundException:
                continue
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in tags.items()]
            results.append(r)
        return results

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('backup')
        resources = []

        for rid in resource_ids:
            try:
                r = client.get_backup_plan(BackupPlanId=rid)
                plan = r.pop('BackupPlan', {})
                r.update(plan)
                resources.append(r)
            except client.exceptions.ResourceNotFoundException:
                continue
        return resources


@resources.register('backup-plan')
class BackupPlan(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'backup'
        enum_spec = ('list_backup_plans', 'BackupPlansList', None)
        detail_spec = ('get_backup_plan', 'BackupPlanId', 'BackupPlanId', None)
        id = 'BackupPlanName'
        name = 'BackupPlanId'
        arn = 'BackupPlanArn'
        config_type = cfn_type = 'AWS::Backup::BackupPlan'
        universal_taggable = object()

    source_mapping = {
        'describe': DescribeBackup,
        'config': ConfigSource
    }


class DescribeVault(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super(DescribeVault, self).augment(resources))

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('backup')
        resources = []
        for rid in resource_ids:
            try:
                resources.append(
                    client.describe_backup_vault(BackupVaultName=rid))
            except client.exceptions.ResourceNotFoundException:
                continue
        return resources


@resources.register('backup-vault')
class BackupVault(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'backup'
        enum_spec = ('list_backup_vaults', 'BackupVaultList', None)
        name = id = 'BackupVaultName'
        arn = 'BackupVaultArn'
        arn_type = 'backup-vault'
        universal_taggable = object()
        config_type = cfn_type = 'AWS::Backup::BackupVault'

    source_mapping = {
        'describe': DescribeVault,
        'config': ConfigSource
    }


@BackupVault.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'EncryptionKeyArn'
