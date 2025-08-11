from ..azure_common import BaseTest


class BackupVaultTest(BaseTest):
    def test_backup_vault_schema_validate(self):
        p = self.load_policy({
            'name': 'test-backup-vault',
            'resource': 'azure.backup-vault'
        }, validate=True)
        self.assertTrue(p)

    def test_backup_vault_find_by_name(self):
        p = self.load_policy({
            'name': 'find-backup-vault-by-name',
            'resource': 'azure.backup-vault',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'value': 'example-backup-vault',
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('example-backup-vault', resources[0]['name'])

