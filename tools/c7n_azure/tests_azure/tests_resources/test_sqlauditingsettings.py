# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import jmespath

from ..azure_common import BaseTest, arm_template


class SqlAuditingSettingsTest(BaseTest):

    def setUp(self):
        super(SqlAuditingSettingsTest, self).setUp()

    def test_sql_database_schema_validate(self):
        for alias in ['azure.sql-auditing-settings', 'azure.sqlauditingsettings']:
            p = self.load_policy({
                'name': 'test-sql-database-schema-validate',
                'resource': alias
            }, validate=True)
            self.assertTrue(p)

    @arm_template('sqlserver.json')
    def test_get_sql_auditing_settings_properties_state_ne_enabled_retention_le_90(self):
        p = self.load_policy({
            'name': 'test-azure-sql-auditing-settings',
            'resource': 'azure.sql-auditing-settings',
            'filters': [{'and': [
                {
                    'type': 'value',
                    'key': 'properties.state',
                    'op': 'ne',
                    'value': 'Enabled',
                },
                {
                    'type': 'value',
                    'key': 'properties.retentionDays',
                    'op': 'le',
                    'value': 90,
                    'value_type': 'integer',
                },
            ]}]
        }, validate=True, cache=True)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(jmespath.search('properties.state', resources[0]), 'Disabled')
