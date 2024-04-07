# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import collections
from unittest.mock import call, Mock
from netaddr import IPSet
from ..azure_common import BaseTest, arm_template, cassette_name
from c7n_azure.resources.postgresql_server import \
    ConfigurationParametersFilter, \
    PostgresqlServerFirewallRulesFilter

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

    @arm_template('postgresql.json')
    def test_find_server_by_configuration(self):
        p = self.load_policy({
            'name': 'test-azure-postgresql-server-configuration',
            'resource': 'azure.postgresql-server',
            'filters': [
                {
                    'type': 'server-configurations',
                    'attrs': [
                        {
                            'type': 'value',
                            'key': 'name',
                            'value': 'log_disconnections',
                        },
                        {
                            'type': 'value',
                            'key': 'properties.value',
                            'value': 'off',
                        }
                    ],
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual('cctestpostgresqlserver2szkrfs64caaw', resources[0]['name'])

    @arm_template('postgresql.json')
    def test_find_server_by_configuration_int(self):
        p = self.load_policy({
            'name': 'test-azure-postgresql-server-configuration-int',
            'resource': 'azure.postgresql-server',
            'filters': [
                {
                    'type': 'server-configurations',
                    'attrs': [
                        {
                            'type': 'value',
                            'key': 'name',
                            'value': 'log_retention_days'
                        },
                        {
                            'type': 'value',
                            'key': 'properties.value',
                            'value': 2,
                            'value_type': 'integer',
                            'op': 'gt'
                        }
                    ]
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual('cctestpostgresqlserver2szkrfs64caaw', resources[0]['name'])

    @cassette_name('firewall-bypass')
    def test_firewall_bypass(self):
        p = self.load_policy({
            'name': 'azure-postgresql-server-firewall-bypass',
            'resource': 'azure.postgresql-server',
            'filters': [
                {'type': 'firewall-bypass',
                 'mode': 'equal',
                 'list': ['AzureServices']}],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertTrue(resources[0]['id'].endswith('/server111postgresaccess'))


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

    def test_query_regular_rules_include_magic(self):
        rules = [IpRange(start_ip_address='10.0.0.0', end_ip_address='10.0.255.255'),
                 IpRange(start_ip_address='8.8.8.8', end_ip_address='8.8.8.8'),
                 IpRange(start_ip_address='0.0.0.0', end_ip_address='0.0.0.0')]
        expected = IPSet(['8.8.8.8', '10.0.0.0/16', '0.0.0.0'])
        self.assertEqual(
            expected,
            self._get_filter(rules, include_magic=True)._query_rules(self.resource)
        )

    def _get_filter(self, rules, mode='equal', include_magic=False):
        data = {mode: ['10.0.0.0/8', '127.0.0.1'], 'include-azure-services': include_magic}
        filter = PostgresqlServerFirewallRulesFilter(data, Mock())
        filter.client = Mock()
        filter.client.firewall_rules.list_by_server.return_value = rules
        return filter


class TestServerSecurityAlertPoliciesFilter(BaseTest):

    def test_server_security_alert_policies_filter(self):
        p = self.load_policy({
            'name': 'test-postgresql-server-filter',
            'resource': 'azure.postgresql-server',
            'filters': [
                {
                    'type': 'security-alert-policies',
                    'attrs': [{
                        'type': 'value',
                        'key': 'properties.state',
                        'value': 'Disabled'
                    }]
                }
            ]
        }, validate=True)

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'postgresqlserver343-red')


class PostgresqlConfigurationParameterFilterTest(BaseTest):
    # one parameter configured in the ARM template with log_connections = 'off'
    @arm_template('postgresql.json')
    def test_server_configuration_parameter(self):
        p = self.load_policy({
            'name': 'test-azure-postgresql-server-configurations',
            'resource': 'azure.postgresql-server',
            'filters': [
                {
                    'type': 'configuration-parameter',
                    'name': 'log_connections',
                    'key': 'value',
                    'op': 'ne',
                    # 'key': "log_connections.value != 'on' or log_disconnections.value != 'on'",
                    'value': 'on'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_int_value_with_regex(self):
        resources = self._get_test_resources()
        data = self._gen_filter_data(123, value_regex='test-(\\d+)', value_type='integer')
        mock_parameter = dict(properties=dict(value='test-123'))

        filter = self._get_filter(data, mock_parameter)
        actual = filter.process(resources)

        # ensure we call azure with the correct resource information
        filter.manager.get_client().configurations.get.assert_called_once_with(
            'test-group-1',
            'test-name-1',
            'test-param'
        )
        self.assertListEqual(resources, actual)

    def test_azure_api_called_only_once_per_resource(self):
        resources = self._get_test_resources(2)

        data1 = self._gen_filter_data('123')
        data2 = self._gen_filter_data('456')
        mock_parameter = dict(properties=dict(value='test-123'))

        filter1 = self._get_filter(data1, mock_parameter)
        filter2 = self._get_filter(data2, mock_parameter)

        # result is unimportant for this test
        # also values are cached on the resource instance so calling two filters on the same
        # resources should not result in additional API calls
        filter1.process(resources)
        filter2.process(resources)

        # ensure we call azure with the correct resource information - and only once per
        # resource even if there are two filters (ensure the cached values are used)
        filter1.manager.get_client().configurations.get.assert_has_calls([
            call('test-group-1', 'test-name-1', 'test-param'),
            call('test-group-2', 'test-name-2', 'test-param')
        ])
        filter2.manager.get_client().configurations.get.assert_not_called()

    def test_date_value(self):
        resources = self._get_test_resources()
        data = self._gen_filter_data('1/1/2023', op='lt', value_type='date')
        # note - str compare would be false
        mock_parameter = dict(properties=dict(value='5/1/2022'))

        filter = self._get_filter(data, mock_parameter)
        actual = filter.process(resources)

        self.assertListEqual(resources, actual)

    def test_all_resources_passing_with_float(self):
        resources = self._get_test_resources()
        data = self._gen_filter_data('2.5', op='gt', value_type='float')
        mock_parameter = dict(properties=dict(value='1.5'))

        filter = self._get_filter(data, mock_parameter)
        actual = filter.process(resources)

        self.assertEqual(0, len(actual))

    def test_list_op_no_match(self):
        resources = self._get_test_resources()
        data = self._gen_filter_data(['1', '2', '3', '4'], op='in')
        mock_parameter = dict(properties=dict(value='5'))

        filter = self._get_filter(data, mock_parameter)
        actual = filter.process(resources)

        self.assertEqual(0, len(actual))

    def test_list_op_matching(self):
        resources = self._get_test_resources()
        data = self._gen_filter_data(['1', '2', '3', '4'], op='in')
        mock_parameter = dict(properties=dict(value='4'))

        filter = self._get_filter(data, mock_parameter)
        actual = filter.process(resources)

        self.assertListEqual(resources, actual)

    def _get_test_resources(self, count=1):
        return [
            dict(name=f'test-name-{i + 1}', resourceGroup=f'test-group-{i + 1}', properties={})
            for i in range(count)
        ]

    def _get_filter(self, data, configurations):
        client = Mock()
        client.configurations.get = Mock(
            return_value=Mock(
                serialize=Mock(return_value=configurations)
            )
        )

        manager = Mock()
        manager.get_client = Mock(return_value=client)

        return ConfigurationParametersFilter(data, manager=manager)

    def _gen_filter_data(self, value, op='eq', value_regex=None, value_type=None,
            name='test-param'):
        return dict(
            type='configuration-parameter',
            key='value',
            name=name,
            value=value,
            op=op,
            **(dict(value_regex=value_regex) if value_regex else {}),
            **(dict(value_type=value_type) if value_type else {}),
        )
