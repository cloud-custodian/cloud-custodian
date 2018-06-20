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

    open_fake_nsgs = [{
        'resourceGroup': 'test_resource_group',
        'name': 'test_nsg',
        'properties': {
            'securityRules': [{
                'properties': {
                    'access': 'Allow'
                }
            }]
        }
    }]
    
    closed_fake_nsgs = [{
        'resourceGroup': 'test_resource_group',
        'name': 'test_nsg',
        'properties': {
            'securityRules': [{
                'properties': {
                    'access': 'Deny'
                }
            }]
        }
    }]

    empty_nsgs = []
    
    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.resources.network_security_group.SecurityRuleFilter.process', return_value=open_fake_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process', return_value=closed_fake_nsgs)
    def test_close_ssh_ports_range(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'FromPort': 8080,
                 'ToPort': 8084}],
            'actions': [
                {'type': 'close'}]})
        p.run()
        rules_action_mock.assert_called_with(self.open_fake_nsgs)

    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.resources.network_security_group.SecurityRuleFilter.process', return_value=empty_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process', return_value=empty_nsgs)
    def test_ports_filter_empty(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'Ports': [93]}],
            'actions': [
                {'type': 'close'}]})
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('networksecuritygroup.json')
    @patch('c7n_azure.resources.network_security_group.SecurityRuleFilter.process', return_value=open_fake_nsgs)
    @patch('c7n_azure.resources.network_security_group.RulesAction.process', return_value=closed_fake_nsgs)
    def test_except_ports_filter_nonempty(self, rules_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'ExceptPorts': [22]}],
            'actions': [
                {'type': 'close'}]})
        p.run()
        rules_action_mock.assert_called_with(self.open_fake_nsgs)

    @arm_template('networksecuritygroup.json')
    def test_invalid_policy_range(self):
        self.assertRaises(ValueError, lambda: self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'FromPort': 22,
                 'ToPort': 20}],
            'actions': [
                {'type': 'close'}]}))

    @arm_template('networksecuritygroup.json')
    def test_invalid_policy_params(self):
        self.assertRaises(ValueError, lambda: self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'FromPort': 22,
                 'ToPort': 20,
                 'ExceptPorts': [20, 30],
                 'Ports': [8080]}],
            'actions': [
                {'type': 'close'}]}))

    @arm_template('networksecuritygroup.json')
    def test_invalid_policy_params_only_ports(self):
        self.assertRaises(ValueError, lambda: self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'ExceptPorts': [20, 30],
                 'Ports': [8080]}],
            'actions': [
                {'type': 'close'}]}))
