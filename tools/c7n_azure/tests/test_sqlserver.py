# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import datetime

from azure_common import BaseTest, cassette_name
from c7n_azure.resources.sqlserver import SqlServerFirewallRulesFilter, \
    SqlServerFirewallBypassFilter
from mock import Mock
from netaddr import IPSet
from parameterized import parameterized

IpRange = collections.namedtuple('IpRange', 'start_ip_address end_ip_address')


class SqlServerTest(BaseTest):

    TEST_DATE = datetime.datetime(2019, 4, 21, 14, 10, 00)

    def test_sql_server_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-policy-assignment',
                'resource': 'azure.sqlserver'
            }, validate=True)
            self.assertTrue(p)

    # run ./templates/provision.sh sqlserver to deploy required resource.
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_metric_elastic_exclude(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'metric',
                 'metric': 'dtu_consumption_percent',
                 'op': 'lt',
                 'aggregation': 'average',
                 'threshold': 10,
                 'timeframe': 72,
                 'filter': "ElasticPoolResourceId eq '*'"
                 }],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_metric_elastic_include(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'metric',
                 'metric': 'dtu_consumption_percent',
                 'op': 'lt',
                 'aggregation': 'average',
                 'threshold': 10,
                 'timeframe': 72,
                 'filter': "ElasticPoolResourceId eq '*'",
                 'no_data_action': 'include'
                 }],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_metric_database(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'metric',
                 'metric': 'dtu_consumption_percent',
                 'op': 'lt',
                 'aggregation': 'average',
                 'threshold': 10,
                 'timeframe': 72,
                 'filter': "DatabaseResourceId eq '*'"
                 }],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @cassette_name('firewall')
    def test_firewall_rules_include_range(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'firewall-rules',
                 'include': ['1.2.2.128-1.2.2.255']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @cassette_name('firewall')
    def test_firewall_rules_not_include_all_ranges(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'firewall-rules',
                 'include': ['0.0.0.0-0.0.0.1']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @cassette_name('firewall')
    def test_firewall_rules_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'firewall-rules',
                 'include': ['1.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @cassette_name('firewall')
    def test_firewall_rules_not_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'firewall-rules',
                 'include': ['2.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @cassette_name('firewall')
    def test_firewall_rules_equal(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'firewall-rules',
                 'equal': ['1.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @cassette_name('firewall')
    def test_firewall_rules_not_equal(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'firewall-rules',
                 'equal': ['0.0.0.0-0.0.0.1', '0.0.0.0-0.0.0.0', '1.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @cassette_name('firewall')
    def test_firewall_bypass(self):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'},
                {'type': 'firewall-bypass',
                 'mode': 'equal',
                 'list': ['AzureServices']}],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))


class SQLServerFirewallFilterTest(BaseTest):

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
        filter = SqlServerFirewallRulesFilter(data, Mock())
        filter.client = Mock()
        filter.client.firewall_rules.list_by_server.return_value = rules
        return filter


class SqlServerFirewallBypassFilterTest(BaseTest):

    resource = {'name': 'test', 'resourceGroup': 'test'}

    scenarios = [
        [[], []],
        [[IpRange(start_ip_address='10.0.0.0', end_ip_address='10.0.255.255'),
          IpRange(start_ip_address='8.8.8.8', end_ip_address='8.8.8.8')], []],
        [[IpRange(start_ip_address='10.0.0.0', end_ip_address='10.0.255.255'),
          IpRange(start_ip_address='8.8.8.8', end_ip_address='8.8.8.8'),
         IpRange(start_ip_address='0.0.0.0', end_ip_address='0.0.0.0')], ['AzureServices']],
    ]

    @parameterized.expand(scenarios)
    def test_run(self, rules, expected):
        f = SqlServerFirewallBypassFilter({'mode': 'equal', 'list': []}, Mock())
        f.client = Mock()
        f.client.firewall_rules.list_by_server.return_value = rules
        self.assertEqual(expected, f._query_bypass(self.resource))
