# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.filters.kms import KmsRelatedFilter
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema


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
        permissions_augment = ("backup:ListTags",)

    source_mapping = {'describe': DescribeBackup, 'config': ConfigSource}


@BackupPlan.action_registry.register('delete')
class BackupPlanDeleteAction(BaseAction):
    """
    Action to delete a backup plan.

    Only works against empty Backup Plans (unless `remove-selections` is
    provided, which will empty them out for you).

    :example:

    .. code-block:: yaml

        policies:
          - name: backup-plan-removal
            resource: aws.backup-plan
            filters:
              - type: value
                key: "Owner"
                value: "{account_id}"
                op: ne
            actions:
              - type: delete
                # If there are any selections still in the plan, remove them first.
                remove-selections: true
    """

    schema = type_schema('delete', **{'remove-selections': {'type': 'boolean'}})
    permissions = ("backup:*",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(
            self.manager.get_model().service
        )

        for r in resources:
            self.process_resource(client, r)

    def get_selections_for_plan(self, client, backup_plan_id):
        selections = []
        paginator = client.get_paginator('list_backup_selections')

        for resp in paginator.paginate(BackupPlanId=backup_plan_id):
            for selection_data in resp.get("BackupSelectionsList", []):
                selections.append(selection_data['SelectionId'])

        return selections

    def process_resource(self, client, resource):
        backup_plan_id = resource['BackupPlanId']
        remove_selections = self.data.get("remove-selections", False)
        existing_selections = self.get_selections_for_plan(client, backup_plan_id)

        if len(existing_selections):
            if not remove_selections:
                self.log.error(
                    f"Error while deleting backup plan {backup_plan_id}, plan is not empty"
                )
                return False

            for selection_id in existing_selections:
                self.manager.retry(
                    client.delete_backup_selection,
                    BackupPlanId=backup_plan_id,
                    SelectionId=selection_id,
                    ignore_err_codes=('ResourceNotFoundException',),
                )

        self.manager.retry(
            client.delete_backup_plan,
            BackupPlanId=backup_plan_id,
            ignore_err_codes=('ResourceNotFoundException',),
        )


class DescribeVault(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, super(DescribeVault, self).augment(resources))

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('backup')
        resources = []
        for rid in resource_ids:
            try:
                resources.append(client.describe_backup_vault(BackupVaultName=rid))
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

    source_mapping = {'describe': DescribeVault, 'config': ConfigSource}


@BackupVault.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'EncryptionKeyArn'


@BackupVault.action_registry.register('delete')
class BackupVaultDeleteAction(BaseAction):
    """
    Action to delete a backup vault.

    Only works against empty Backup Vaults (unless `remove-recovery-points` is
    provided, which will empty them out for you).

    :example:

    .. code-block:: yaml

        policies:
          - name: backup-vault-removal
            resource: aws.backup-vault
            filters:
              - type: value
                key: "BackupVaultName"
                value: "test-vault"
            actions:
              - type: delete
                # If there are any recovery points still in the vault, remove them first.
                remove-recovery-points: true
    """

    schema = type_schema('delete', **{'remove-recovery-points': {'type': 'boolean'}})
    permissions = ("backup:*",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(
            self.manager.get_model().service
        )

        for r in resources:
            self.process_resource(client, r)

    def get_recovery_points_for_vault(self, client, backup_vault_name):
        recovery_points = []
        paginator = client.get_paginator('list_recovery_points_by_backup_vault')

        for resp in paginator.paginate(BackupVaultName=backup_vault_name):
            for recovery_point_data in resp.get("RecoveryPoints", []):
                recovery_points.append(recovery_point_data['RecoveryPointArn'])

        return recovery_points

    def process_resource(self, client, resource):
        backup_vault_name = resource['BackupVaultName']
        remove_recovery_points = self.data.get("remove-recovery-points", False)
        existing_recovery_points = self.get_recovery_points_for_vault(client, backup_vault_name)

        if len(existing_recovery_points):
            if not remove_recovery_points:
                self.log.error(
                    f"Error while deleting backup vault {backup_vault_name}, vault is not empty"
                )
                return False

            for recovery_point_arn in existing_recovery_points:
                self.manager.retry(
                    client.delete_recovery_point,
                    BackupVaultName=backup_vault_name,
                    RecoveryPointArn=recovery_point_arn,
                    ignore_err_codes=('ResourceNotFoundException',),
                )

        self.manager.retry(
            client.delete_backup_vault,
            BackupVaultName=backup_vault_name,
            ignore_err_codes=('ResourceNotFoundException',),
        )
