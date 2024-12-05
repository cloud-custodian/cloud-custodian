# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template


class MySQLFlexibleServerTest(BaseTest):
    def test_mysql_flexibleserver_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-mysql-flexibleserver',
            'resource': 'azure.mysql-flexibleserver'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('mysqlflexible.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-mysql-flexibleserver',
            'resource': 'azure.mysql-flexibleserver',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestmyflexibleserveradeqcukmdv6zs'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('mysqlflexible.json')
    def test_server_server_parameter(self):
        p = self.load_policy({
            'name': 'test-azure-mysql-flexibleserver-configurations',
            'resource': 'azure.mysql-flexibleserver',
            'filters': [
                {
                    'type': 'server-parameter',
                    'name': 'tls_version',
                    'key': 'value',
                    'op': 'ne',
                    'value': 'TLSv1.2'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)
