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

import datetime

from azure_common import BaseTest, cassette_name, arm_template
from mock import patch
from netaddr import IPRange, IPSet


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
                 'include': ['0.0.0.0-0.0.0.0']}],
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
                 'include': ['0.0.0.0-0.0.0.0', '0.0.0.0-0.0.0.1']}],
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
                 'equal': ['0.0.0.0-0.0.0.0', '1.2.2.128/25']}],
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

    @patch('azure.mgmt.sql.operations.firewall_rules_operations.'
           'FirewallRulesOperations.create_or_update')
    @cassette_name('firewall_action')
    @arm_template('sqlserver.json')
    def test_set_ip_range_filter_replace(self, update_mock):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'append': False,
                 'ip-rules': ['0.0.0.0/1', '11.12.13.14', '21.22.23.24']
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(1, len(resources))

        # one call per IP *range*
        self.assertEqual(3, len(update_mock.mock_calls))
        name, args, kwargs = update_mock.mock_calls[0]

        # verify other fields seem legitimate
        self.assertEqual(resources[0]['resourceGroup'], args[0])
        self.assertEqual(resources[0]['name'], args[1])
        self.assertEqual('c7n', args[2][:3])

        # now check all the IP's
        ips = IPSet()
        for r in [IPRange(args[3], args[4]) for _, args, _ in update_mock.mock_calls]:
            ips.add(r)

        self.assertEqual(IPSet(['0.0.0.0/1', '11.12.13.14', '21.22.23.24']), ips)

    @patch('azure.mgmt.sql.operations.firewall_rules_operations.'
           'FirewallRulesOperations.create_or_update')
    @cassette_name('firewall_action')
    @arm_template('sqlserver.json')
    def test_set_ip_range_filter_append(self, update_mock):
        p = self.load_policy({
            'name': 'test-azure-sql-server',
            'resource': 'azure.sqlserver',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsqlserver*'}],
            'actions': [
                {'type': 'set-firewall-rules',
                 'ip-rules': ['0.0.0.0/1', '11.12.13.14', '21.22.23.24']
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(1, len(resources))

        # one call per IP *range*
        self.assertEqual(3, len(update_mock.mock_calls))
        name, args, kwargs = update_mock.mock_calls[0]

        # verify other fields seem legitimate
        self.assertEqual(resources[0]['resourceGroup'], args[0])
        self.assertEqual(resources[0]['name'], args[1])
        self.assertEqual('c7n', args[2][:3])

        # now check all the IP's
        ips = IPSet()
        for r in [IPRange(args[3], args[4]) for _, args, _ in update_mock.mock_calls]:
            ips.add(r)

        self.assertEqual(IPSet(['0.0.0.0/1', '11.12.13.14', '21.22.23.24']), ips)
