# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class BackupTest(BaseTest):

    def test_augment(self):
        factory = self.replay_flight_data("test_backup_augment")
        p = self.load_policy({
            'name': 'all-backup',
            'resource': 'aws.backup-plan'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        plan = resources.pop()
        self.assertEqual(
            plan['Tags'],
            [{'Key': 'App', 'Value': 'Backups'}])
        self.assertTrue('Rules' in plan)

        self.assertEqual(
            p.resource_manager.get_arns([plan]),
            [plan['BackupPlanArn']])
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


class BackupVaultTest(BaseTest):

    def test_backup_get_resources(self):
        factory = self.replay_flight_data('test_backup_vault_get_resources')
        p = self.load_policy({
            "name": "backup-vault", "resource": "backup-vault"},
            session_factory=factory)
        resources = p.resource_manager.get_resources(['Default'])
        self.assertEqual(
            resources[0]['Tags'],
            [{'Key': 'target-tag', 'Value': 'target-value'}])

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
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/aws/backup'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['EncryptionKeyArn'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/aws/backup')


    def test_backup_vault_cross_account_filter(self):
        session_factory = self.replay_flight_data('test_backup_vault_cross_account_filter')
        p = self.load_policy(
            {
                'name': 'test-backup-vault-cross-account-filter',
                'resource': 'backup-vault',
                'filters': [
                    {
                        'type': 'cross-account',
                        'blacklist_orgids': ["o-4amkskbcf1"]
                    },
                    {
                        'type': 'value',
                        'key': 'BackupVaultName',
                        'value': 'c7n-test-backup-vault',
                        'op': 'equal'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['BackupVaultName'], 'c7n-test-backup-vault')


    def test_backup_vault_cross_account_filter_remove(self):
        session_factory = self.replay_flight_data('test_backup_vault_cross_account_filter_remove')
        p = self.load_policy(
            {
                'name': 'test-backup-vault-cross-account-filter-remove',
                'resource': 'backup-vault',
                'filters': [
                    {
                        'type': 'cross-account',
                        'blacklist_orgids': ["o-4amkskbcf1"]
                    },
                    {
                        'type': 'value',
                        'key': 'BackupVaultName',
                        'value': 'c7n-test-backup-vault',
                        'op': 'equal'
                    }
                ],
                'actions': [{
                    'type': 'remove-statements',
                    'statement_ids': 'matched'
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['BackupVaultName'], 'c7n-test-backup-vault')
