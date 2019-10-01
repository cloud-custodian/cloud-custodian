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

from ..azure_common import BaseTest, arm_template


class NetworkSecurityGroupTest(BaseTest):
    def setUp(self):
        super(NetworkSecurityGroupTest, self).setUp()

    def test_network_security_group_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-network-security-group',
                'resource': 'azure.networksecuritygroup',
                'filters': [
                    {'type': 'ingress',
                     'ports': '80',
                     'access': 'Allow'},
                    {'type': 'egress',
                     'ports': '22',
                     'ipProtocol': 'TCP',
                     'access': 'Allow'}
                ],
                'actions': [
                    {'type': 'open',
                     'ports': '1000-1100',
                     'direction': 'Inbound'},
                    {'type': 'close',
                     'ports': '1000-1100',
                     'direction': 'Inbound'},

                ]
            }, validate=True)
            self.assertTrue(p)

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
                 'value': 'c7n-nsg'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('networksecuritygroup.json')
    def test_allow_single_port(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'c7n-nsg'},
                {'type': 'ingress',
                 'ports': '80',
                 'access': 'Allow'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('networksecuritygroup.json')
    def test_allow_multiple_ports(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'c7n-nsg'},
                {'type': 'ingress',
                 'ports': '80,8080-8084,88-90',
                 'match': 'all',
                 'access': 'Allow'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('networksecuritygroup.json')
    def test_allow_ports_range_any(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'c7n-nsg'},
                {'type': 'ingress',
                 'ports': '40-100',
                 'match': 'any',
                 'access': 'Allow'}]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('networksecuritygroup.json')
    def test_deny_port(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'c7n-nsg'},
                {'type': 'ingress',
                 'ports': '8086',
                 'access': 'Deny'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('networksecuritygroup.json')
    def test_egress_policy_protocols(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'c7n-nsg'},
                {'type': 'egress',
                 'ports': '22',
                 'ipProtocol': 'TCP',
                 'access': 'Allow'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'c7n-nsg'},
                {'type': 'egress',
                 'ports': '22',
                 'ipProtocol': 'UDP',
                 'access': 'Allow'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('networksecuritygroup.json')
    def test_open_ports(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'c7n-nsg'},
            ],
            'actions': [
                {
                    'type': 'open',
                    'ports': '1000-1100',
                    'direction': 'Inbound'}
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'c7n-nsg'},
                {'type': 'ingress',
                 'ports': '1000-1100',
                 'match': 'any',
                 'access': 'Deny'}]
        })

        resources = p.run()
        self.assertEqual(len(resources), 0)
