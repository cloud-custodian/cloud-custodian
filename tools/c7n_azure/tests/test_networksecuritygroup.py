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


class NetworkSecurityGroupTest(BaseTest):
    def setUp(self):
        super(NetworkSecurityGroupTest, self).setUp()

    @arm_template('networksecuritygroup.json')
    def test_close_ssh_ports_range(self):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'FromPort': 8080,
                 'ToPort': 8084}],
            'actions': [
                {'type': 'close'}]})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'tabarlow-test-open-ssh')
        self.assertEqual(len(resources[0]['properties']['securityRules']), 1)

    @arm_template('networksecuritygroup.json')
    def test_ports_filter_empty(self):
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
    def test_only_ports_filter_nonempty(self):
        p = self.load_policy({
            'name': 'test-azure-network-security-group',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'OnlyPorts': [22]}],
            'actions': [
                {'type': 'close'}]})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'tabarlow-test-open-ssh')
        self.assertEqual(len(resources[0]['properties']['securityRules']), 1)


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
                 'OnlyPorts': [20, 30],
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
                 'OnlyPorts': [20, 30],
                 'Ports': [8080]}],
            'actions': [
                {'type': 'close'}]}))


