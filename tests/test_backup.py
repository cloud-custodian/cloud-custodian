# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class BackupTest(BaseTest):
    def test_augment(self):
        factory = self.replay_flight_data("test_backup_augment")
        p = self.load_policy(
            {'name': 'all-backup', 'resource': 'aws.backup-plan'}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        plan = resources.pop()
        self.assertEqual(plan['Tags'], [{'Key': 'App', 'Value': 'Backups'}])
        self.assertTrue('Rules' in plan)

        self.assertEqual(p.resource_manager.get_arns([plan]), [plan['BackupPlanArn']])
        resources = p.resource_manager.get_resources([plan['BackupPlanId']])
        self.assertEqual(len(resources), 1)


class BackupPlanTest(BaseTest):
    def test_backup_plan_tag_untag(self):
        factory = self.replay_flight_data("test_backup_plan_tag_untag")
        p = self.load_policy(
            {
                "name": "backup-plan-tag",
                "resource": "backup-plan",
                "filters": [{"tag:target-tag": "present"}],
                "actions": [
                    {"type": "remove-tag", "tags": ["target-tag"]},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("backup")
        tag = client.list_tags(ResourceArn=resources[0]['BackupPlanArn'])
        self.assertEqual(len(tag.get('Tags')), 0)

    def test_backup_plan_delete(self):
        factory = self.replay_flight_data("test_backup_plan_delete")
        p = self.load_policy(
            {
                "name": "backup-plan-delete",
                "resource": "backup-plan",
                "filters": [
                    {
                        "type": "value",
                        "key": "BackupPlanName",
                        "value": "test-backup-plan",
                    },
                ],
                "actions": [
                    {
                        "type": "delete",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the backup plan was deleted
        client = factory().client("backup")
        plans = client.list_backup_plans().get('BackupPlansList', [])
        plan_ids = [p['BackupPlanId'] for p in plans]
        self.assertNotIn(resources[0]['BackupPlanId'], plan_ids)

    def test_backup_plan_delete_with_selections_fails(self):
        factory = self.replay_flight_data("test_backup_plan_delete_with_selections_fails")
        p = self.load_policy(
            {
                "name": "backup-plan-delete",
                "resource": "backup-plan",
                "filters": [
                    {
                        "type": "value",
                        "key": "BackupPlanName",
                        "value": "test-backup-plan",
                    },
                ],
                "actions": [
                    {
                        "type": "delete",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the backup plan still exists (deletion should have failed)
        client = factory().client("backup")
        plans = client.list_backup_plans().get('BackupPlansList', [])
        plan_ids = [p['BackupPlanId'] for p in plans]
        self.assertIn(resources[0]['BackupPlanId'], plan_ids)

    def test_backup_plan_delete_with_remove_selections(self):
        factory = self.replay_flight_data("test_backup_plan_delete_with_remove_selections")
        p = self.load_policy(
            {
                "name": "backup-plan-delete",
                "resource": "backup-plan",
                "filters": [
                    {
                        "type": "value",
                        "key": "BackupPlanName",
                        "value": "test-backup-plan",
                    },
                ],
                "actions": [
                    {
                        "type": "delete",
                        "remove-selections": True,
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the backup plan was deleted
        client = factory().client("backup")
        plans = client.list_backup_plans().get('BackupPlansList', [])
        plan_ids = [p['BackupPlanId'] for p in plans]
        self.assertNotIn(resources[0]['BackupPlanId'], plan_ids)


class BackupVaultTest(BaseTest):
    def test_backup_get_resources(self):
        factory = self.replay_flight_data('test_backup_vault_get_resources')
        p = self.load_policy(
            {"name": "backup-vault", "resource": "backup-vault"}, session_factory=factory
        )
        resources = p.resource_manager.get_resources(['Default'])
        self.assertEqual(resources[0]['Tags'], [{'Key': 'target-tag', 'Value': 'target-value'}])

    def test_backup_vault_tag_untag(self):
        factory = self.replay_flight_data("test_backup_vault_tag_untag")
        p = self.load_policy(
            {
                "name": "backup-vault-tag",
                "resource": "backup-vault",
                "filters": [{"tag:target-tag": "present"}],
                "actions": [
                    {"type": "remove-tag", "tags": ["target-tag"]},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("backup")
        tag = client.list_tags(ResourceArn=resources[0]['BackupVaultArn'])
        self.assertEqual(len(tag.get('Tags')), 0)

    def test_backup_vault_kms_filter(self):
        session_factory = self.replay_flight_data('test_backup_vault_kms_filter')
        kms = session_factory().client('kms')
        p = self.load_policy(
            {
                'name': 'test-backup-vault-kms-filter',
                'resource': 'backup-vault',
                'filters': [
                    {'type': 'kms-key', 'key': 'c7n:AliasName', 'value': 'alias/aws/backup'}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['EncryptionKeyArn'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/aws/backup')

    def test_backup_vault_delete(self):
        factory = self.replay_flight_data("test_backup_vault_delete")
        p = self.load_policy(
            {
                "name": "backup-vault-delete",
                "resource": "backup-vault",
                "filters": [
                    {
                        "type": "value",
                        "key": "BackupVaultName",
                        "value": "test-backup-vault",
                    },
                ],
                "actions": [
                    {"type": "delete"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the backup vault was deleted
        client = factory().client("backup")
        vaults = client.list_backup_vaults().get('BackupVaultList', [])
        vault_names = [v['BackupVaultName'] for v in vaults]
        self.assertNotIn(resources[0]['BackupVaultName'], vault_names)

    def test_backup_vault_delete_with_recovery_points_fails(self):
        factory = self.replay_flight_data("test_backup_vault_delete_with_recovery_points_fails")
        p = self.load_policy(
            {
                "name": "backup-vault-delete",
                "resource": "backup-vault",
                "filters": [
                    {
                        "type": "value",
                        "key": "BackupVaultName",
                        "value": "test-backup-vault",
                    },
                ],
                "actions": [
                    {"type": "delete"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the backup vault still exists (deletion should have failed)
        client = factory().client("backup")
        vaults = client.list_backup_vaults().get('BackupVaultList', [])
        vault_names = [v['BackupVaultName'] for v in vaults]
        self.assertIn(resources[0]['BackupVaultName'], vault_names)

    def test_backup_vault_delete_with_remove_recovery_points(self):
        factory = self.replay_flight_data("test_backup_vault_delete_with_remove_recovery_points")
        p = self.load_policy(
            {
                "name": "backup-vault-delete",
                "resource": "backup-vault",
                "filters": [
                    {
                        "type": "value",
                        "key": "BackupVaultName",
                        "value": "test-backup-vault",
                    },
                ],
                "actions": [
                    {
                        "type": "delete",
                        "remove-recovery-points": True,
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Verify the backup vault was deleted
        client = factory().client("backup")
        vaults = client.list_backup_vaults().get('BackupVaultList', [])
        vault_names = [v['BackupVaultName'] for v in vaults]
        self.assertNotIn(resources[0]['BackupVaultName'], vault_names)
