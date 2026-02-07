# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from ..azure_common import BaseTest, arm_template


class NetworkSecurityGroupTest(BaseTest):

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
                 'source': '*',
                 'access': 'Allow'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r["name"] for r in resources[0]['c7n:matched-ingress-security-rules']}, {'test1'}
        )

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
        self.assertEqual(
            {r["name"] for r in resources[0]['c7n:matched-ingress-security-rules']},
            {'test1', 'test2', 'test6'}
        )

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
        self.assertEqual(
            {r["name"] for r in resources[0]['c7n:matched-ingress-security-rules']},
            {'test1', 'test6'}
        )

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
        self.assertEqual(
            {r["name"] for r in resources[0]['c7n:matched-ingress-security-rules']}, {'test3'}
        )

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
                 'destination': '*',
                 'access': 'Allow'}],
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r["name"] for r in resources[0]['c7n:matched-egress-security-rules']}, {'test5'}
        )

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
    @patch('uuid.uuid1', return_value='00000000-0000-0000-0000-000000000000')
    def test_open_ports(self, _1):
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

    @arm_template('networksecuritygroup.json')
    def test_icmp_protocol(self):
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
                 'ports': '0-65535',
                 'ipProtocol': 'ICMP',
                 'source': '*',
                 'access': 'Deny'}]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r["name"] for r in resources[0]['c7n:matched-ingress-security-rules']}, {'test1'}
        )

    @arm_template('networksecuritygroup.json')
    def test_cidr_only_match(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'match': 'all',
                 'access': 'Deny',
                 'Cidr': {
                    'value_type': 'cidr',
                    'op': 'in',
                    'value': ['10.0.0.0/8'],
                    'ipType': 'destination'
        }}]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r["name"] for r in resources[0]['c7n:matched-ingress-security-rules']}, {'test4'}
        )

    @arm_template('networksecuritygroup.json')
    def test_cidr_only_no_match(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'match': 'all',
                 'access': 'Deny',
                 'Cidr': {
                    'value_type': 'cidr',
                    'op': 'in',
                    'value': ['10.0.0.0/8'],
                    'ipType': 'source'
        }}]
        })

        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('networksecuritygroup.json')
    def test_cidr_and_ingress_match(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'match': 'all',
                 'Cidr': {
                    'value_type': 'cidr',
                    'op': 'in',
                    'value': ['10.0.0.0/8'],
                    'ipType': 'source'
                },
                'ports': '22',
                'ipProtocol': 'TCP',
                'access': 'Deny'
                }]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r["name"] for r in resources[0]['c7n:matched-ingress-security-rules']}, {'test4'}
        )

    @arm_template('networksecuritygroup.json')
    def test_cidr_and_ingress_no_match(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                 'match': 'all',
                 'Cidr': {
                    'value_type': 'cidr',
                    'op': 'in',
                    'value': ['10.0.0.0/8'],
                    'ipType': 'source'
                },
                'ports': '10000',
                'ipProtocol': 'TCP',
                'source': '*',
                'access': 'Allow'}]
        })

        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('networksecuritygroup.json')
    def test_no_cidr_no_ports(self):
        # TODO: this test is insufficient, because the cassette loaded here only contains an empty
        # response. Also, this is not the behavior on master. On master, this filter would match
        # any NSG for which *every port* was open. We should add a test that confirms this and then
        # duplicate the behavior here.
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                'access': 'Allow'}]
        })

        resources = p.run()
        # Do we really want this behavior?
        self.assertEqual(len(resources), 0)


class NetworkSecurityGroupFlowLogsFilterTest(BaseTest):
    def test_flow_log_filter_all(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {
                    'type': 'flow-logs',
                    'key': 'length(logs)',
                    'value': 0
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_flow_log_filter_matching(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {
                    'type': 'flow-logs',
                    'key': 'length(logs)',
                    'op': 'gt',
                    'value': 0
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
