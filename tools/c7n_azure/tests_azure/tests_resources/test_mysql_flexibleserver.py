# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import call, Mock

from ..azure_common import BaseTest, arm_template
from c7n_azure.resources.mysql_flexibleserver import \
    ConfigurationParametersFilter


class MySQLFlexiblerServerTest(BaseTest):

    def test_mysql_flexibleserver_schema_validate(self):
        p = self.load_policy({
            'name': 'test-mysql-flexiblerserver-schema-validate',
            'resource': 'azure.mysql-flexibleserver'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('mysql_flexibleserver.json')
    def test_find_server_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-mysql-flexibleserver',
            'resource': 'azure.mysql-flexibleserver',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestmysqlflexibleserver*'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class MySqlFlexibleServerConfigurationParameterFilterTest(BaseTest):
    @arm_template('mysqlflexibleserver.json')
    def test_server_configuration_parameter(self):
        p = self.load_policy({
            'name': 'test-azure-mysql-flexibleserver-configurations',
            'resource': 'azure.mysql-flexibleserver',
            'filters': [
                {
                    'type': 'configuration-parameter',
                    'name': 'tls_version',
                    'key': 'value',
                    'op': 'ne',
                    'value': 'TLSv1.2'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)