# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import collections
from netaddr import IPSet
from mock import Mock
from ..azure_common import BaseTest, arm_template
from c7n_azure.resources.postgresql_server import PostgresqlServerFirewallRulesFilter

IpRange = collections.namedtuple('IpRange', 'start_ip_address end_ip_address')

PORTAL_IPS = ['104.42.195.92',
              '40.76.54.131',
              '52.176.6.30',
              '52.169.50.45',
              '52.187.184.26']
AZURE_CLOUD_IPS = ['0.0.0.0']


class PostgresqlServerTest(BaseTest):

    def test_postgresql_server_schema_validate(self):
        p = self.load_policy({
            'name': 'test-postgresql-server-schema-validate',
            'resource': 'azure.postgresql-server'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('postgresql.json')
    def test_find_server_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-postgresql-server',
            'resource': 'azure.postgresql-server',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestpostgresqlserver*'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class PostgresqlServerFirewallFilterTest(BaseTest):

    resource = {'name': 'test', 'resourceGroup': 'test'}

    def test_query_empty_rules(self):
        rules = []
        expected = IPSet()
        self.assertEqual(expected, self._get_filter(rules)._query_rules(self.resource))

    def test_query_regular_rules(self):
        rules = [IpRange(start_ip_address='10.0.0.0', end_ip_address='10.0.255.255'),
                 IpRange(start_ip_address='8.8.8.8', end_ip_address='8.8.8.8')]
        expected = IPSet(['8.8.8.8', '10.0.0.0/16'])
        self.assertEqual(expected, self._get_filter(rules)._query_rules(self.resource))

    def test_query_regular_rules_with_magic(self):
        rules = [IpRange(start_ip_address='10.0.0.0', end_ip_address='10.0.255.255'),
                 IpRange(start_ip_address='8.8.8.8', end_ip_address='8.8.8.8'),
                 IpRange(start_ip_address='0.0.0.0', end_ip_address='0.0.0.0')]
        expected = IPSet(['8.8.8.8', '10.0.0.0/16'])
        self.assertEqual(expected, self._get_filter(rules)._query_rules(self.resource))

    def _get_filter(self, rules, mode='equal'):
        data = {mode: ['10.0.0.0/8', '127.0.0.1']}
        filter = PostgresqlServerFirewallRulesFilter(data, Mock())
        filter.client = Mock()
        filter.client.firewall_rules.list_by_server.return_value = rules
        return filter
