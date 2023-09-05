# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from botocore.exceptions import ClientError

from c7n.actions import RemovePolicyBase
from c7n.manager import resources
from c7n.filters import CrossAccountAccessFilter
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


@BackupVault.filter_registry.register('cross-account')
class BackupCrossAccountFilter(CrossAccountAccessFilter):
    """
    Filter to return all AWS Backup Vaults with cross account access permissions

    :example:

        .. code-block::yaml

            policies:
              - name: check-backup-vaults-cross-account
                resource: aws.backup-vault
                filters:
                  - type: cross-account
              - name: check-backup-vaults-cross-account-whitelist
                resource: aws.backup-vault
                filters:
                  - type: cross-account
                    whitelist:
                      - allow-account-1
                      - allow-account-2
              - name: check-backup-vaults-cross-account-whitelist-orgid
                resource: aws.backup-vault
                filters:
                  - type: cross-account
                    whitelist_orgids:
                      - allow-orgid-1
                      - allow-orgid-2
              - name: check-backup-vaults-cross-account-blacklist
                resource: aws.backup-vault
                filters:
                  - type: cross-account
                    blacklist:
                      - deny-account-1
                      - deny-account-2
              - name: check-backup-vaults-cross-account-blacklist-orgid
                resource: aws.backup-vault
                filters:
                  - type: cross-account
                    blacklist_orgids:
                      - deny-orgid-1
                      - deny-orgid-2
    """

    permissions = ('backup:GetBackupVaultAccessPolicy')

    def process(self, resources, event=None):
        def _augment(r):
            client = local_session(self.manager.session_factory).client('backup')
            try:
                r['Policy'] = client.get_backup_vault_access_policy(
                    BackupVaultName=r['BackupVaultName']
                )['Policy']
                return r
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    self.log.warning(
                        f'Policy not found for {r["BackupVaultName"]}'
                    )

        with self.executor_factory(max_workers=3) as w:
            resources = list(
                filter(None, w.map(_augment, resources))
            )

        return super(BackupCrossAccountFilter, self).process(resources, event)


@BackupVault.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """
    Action to remove policy statements from AWS Backup Vault access policy

    :example:

        .. code-block::yaml

            policies:
              - name: check-backup-vaults-cross-account-remove
                resource: aws.backup-vault
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    permissions = ('backup:GetBackupVaultAccessPolicy', 'backup:SetBackupVaultAccessPolicy')

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('backup')
        for r in resources:
            try:
                results += filter(None, [self.process_resource(client, r)])
            except Exception:
                self.log.exception(f'Error processing Backup Vault: {r["BackupVaultName"]}')

    def process_resource(self, client, resource):
        if 'Policy' not in resource.keys():
            try:
                resource['Policy'] = client.get_backup_vault_access_policy(
                    BackupVaultName=resource['BackupVaultName']
                )['Policy']
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    self.log.error(
                        f'Policy not found for {resource["BackupVaultName"]}'
                    )
                    raise e

        if not resource['Policy']:
            return

        policy = json.loads(resource['Policy'])
        statements, found = self.process_policy(
            policy, resource, CrossAccountAccessFilter.annotation_key
        )

        if not found:
            return

        if not statements:
            client.delete_backup_vault_access_policy(BackupVaultName=resource['BackupVaultName'])
        else:
            client.set_backup_vault_access_policy(
                BackupVaultName=resource['BackupVaultName'],
                policy={'Policy': json.dumps(policy)}
            )

        return {
            'Name': resource['BackupVaultName'],
            'State': 'PolicyRemoved',
            'Statements': found
        }
