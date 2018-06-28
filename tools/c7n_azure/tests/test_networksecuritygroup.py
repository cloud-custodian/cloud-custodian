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
from azure_common import BaseTest, arm_template
from c7n.filters.core import PolicyValidationError
from c7n_azure.resources.network_security_group \
    import FROM_PORT, TO_PORT, PORTS, EXCEPT_PORTS, IP_PROTOCOL
from mock import patch


class NetworkSecurityGroupTest(BaseTest):
    def setUp(self):
        super(NetworkSecurityGroupTest, self).setUp()

    @arm_template('networksecuritygroup.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'anzoloch-test-vm-nsg'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    fake_nsgs = [{
        'resourceGroup': 'test_resource_group',
        'name': 'test_nsg',
        'properties': {
            'securityRules': [
                {
                    'name': 'test_1',
                    'properties': {
                        'direction': 'Inbound',
                        'access': 'Allow',
                        'protocol': 'TCP',
                        'destinationPortRange': '8081-8083'
                    }
                },
                {
                    'name': 'test_2',
                    'properties': {
                        'direction': 'Inbound',
                        'access': 'Allow',
                        'protocol': 'TCP',
                        'destinationPortRange': '22'
                    }
                },
                {
                    'name': 'test_3',
                    'properties': {
                        'direction': 'Inbound',
                        'access': 'Allow',
                        'protocol': 'UDP',
                        'destinationPortRange': '8081-8089'
                    }
                },
                {
                    'name': 'test_4',
                    'properties': {
                        'direction': 'Inbound',
                        'access': 'Allow',
                        'protocol': 'UDP',
                        'destinationPortRanges': ['10-12', '14-15', '16-19']
                    }
                },
            ]
        }
    }]

    empty_nsgs = []

    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process',
        return_value='')
    def test_port_range(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 FROM_PORT: 8080,
                 TO_PORT: 8084}],
            'actions': [
                {'type': 'close'}]})
        p.run()
        expected = [{'resourceGroup': 'test_resource_group',
            'name': 'test_nsg',
            'properties': {
                'securityRules': [
                    {
                        'name': 'test_1',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'TCP',
                            'destinationPortRange': '8081-8083'
                        }
                    }
                ]
            }}
        ]
        rules_action_mock.assert_called_with(expected)

    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process',
        return_value='')
    def test_ports_filter_empty(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 PORTS: [93]}],
            'actions': [
                {'type': 'close'}]})
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process',
        return_value='')
    def test_except_ports_filter_nonempty(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 EXCEPT_PORTS: [22]}],
            'actions': [
                {'type': 'close'}]})
        p.run()
        expected = [{
            'resourceGroup': 'test_resource_group',
            'name': 'test_nsg',
            'properties': {
                'securityRules': [
                    {
                        'name': 'test_1',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'TCP',
                            'destinationPortRange': '8081-8083'
                        }
                    },
                    {
                        'name': 'test_3',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'UDP',
                            'destinationPortRange': '8081-8089'
                        }
                    },
                    {
                        'name': 'test_4',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'UDP',
                            'destinationPortRanges': ['10-12', '14-15', '16-19']
                        }
                    },
                ]
            }}]
        rules_action_mock.assert_called_with(expected)

    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process',
        return_value='')
    def test_protocol_filter(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 IP_PROTOCOL: 'UDP'}],
            'actions': [
                {'type': 'close'}]})
        p.run()
        expected = [{
            'resourceGroup': 'test_resource_group',
            'name': 'test_nsg',
            'properties': {
                'securityRules': [
                    {
                        'name': 'test_3',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'UDP',
                            'destinationPortRange': '8081-8089'
                        }
                    },
                    {
                        'name': 'test_4',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'UDP',
                            'destinationPortRanges': ['10-12', '14-15', '16-19']
                        }
                    },
                ]
            }}]
        rules_action_mock.assert_called_with(expected)

    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process',
        return_value='')
    def test_protocol_and_range_filter(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 IP_PROTOCOL: 'UDP',
                 FROM_PORT: 8081,
                 TO_PORT: 8089}],
            'actions': [
                {'type': 'close'}]})
        p.run()
        expected = [{
            'resourceGroup': 'test_resource_group',
            'name': 'test_nsg',
            'properties': {
                'securityRules': [
                    {
                        'name': 'test_3',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'UDP',
                            'destinationPortRange': '8081-8089'
                        }
                    }
                ]
            }}]
        rules_action_mock.assert_called_with(expected)

    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process',
        return_value='')
    def test_protocol_or_range_filter(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 IP_PROTOCOL: 'UDP',
                 'match-operator': 'or',
                 PORTS: [22]}],
            'actions': [
                {'type': 'close'}]})
        p.run()
        expected = [{
            'resourceGroup': 'test_resource_group',
            'name': 'test_nsg',
            'properties': {
                'securityRules': [
                    {
                        'name': 'test_2',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'TCP',
                            'destinationPortRange': '22'
                        }
                    },
                    {
                        'name': 'test_3',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'UDP',
                            'destinationPortRange': '8081-8089'
                        }
                    },
                    {
                        'name': 'test_4',
                        'properties': {
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': 'UDP',
                            'destinationPortRanges': ['10-12', '14-15', '16-19']
                        }
                    },
                ]
            }}]
        rules_action_mock.assert_called_with(expected)

    @arm_template('networksecuritygroup.json')
    def test_invalid_policy_range(self):
        self.assertRaises(PolicyValidationError, lambda: self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 FROM_PORT: 22,
                 TO_PORT: 20}],
            'actions': [
                {'type': 'close'}]}))

    @arm_template('networksecuritygroup.json')
    def test_invalid_policy_params(self):
        self.assertRaises(PolicyValidationError, lambda: self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 FROM_PORT: 22,
                 TO_PORT: 20,
                 EXCEPT_PORTS: [20, 30],
                 PORTS: [8080]}],
            'actions': [
                {'type': 'close'}]}))

    @arm_template('networksecuritygroup.json')
    def test_invalid_policy_params_only_ports(self):
        self.assertRaises(PolicyValidationError, lambda: self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 EXCEPT_PORTS: [20, 30],
                 PORTS: [8080]}],
            'actions': [
                {'type': 'close'}]}))
