# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class MySQLTest(BaseTest):
    def test_azure_mysql_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-mysql',
            'resource': 'azure.mysql'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('mysql.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-mysql',
            'resource': 'azure.mysql',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'ccmysql*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('mysql.json')
    def test_server_server_configurations_parameters(self):
        p = self.load_policy({
            'name': 'test-azure-mysql-server-configurations',
            'resource': 'azure.mysql',
            'filters': [
                {
                    'type': 'server-configuration',
                    'name': 'audit_log_enabled',
                    'key': 'value',
                    'op': 'ne',
                    'value': 'ON'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class MySQLSecurityAlertPoliciesFilterTest(BaseTest):
    def test_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-mysql',
            'resource': 'azure.mysql',
            'filters': [
                {'type': 'security-alert-policy',
                 'key': 'state',
                 'op': 'eq',
                 'value': 'Enabled'}]
        }, validate=True)
        self.assertTrue(p)

    def test_query(self):
        p = self.load_policy({
            'name': 'test-azure-mysql',
            'resource': 'azure.mysql',
            'filters': [
                {'type': 'security-alert-policy',
                 'key': 'state',
                 'op': 'eq',
                 'value': 'Enabled'}]
        })

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], '344-mysql-server-green')
