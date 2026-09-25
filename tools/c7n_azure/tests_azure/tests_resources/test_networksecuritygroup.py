# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock, patch

from parameterized import parameterized
from pytest_terraform import terraform

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
                    {'type': 'remove-rules',
                     'ingress': 'matched'},
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

    @parameterized.expand([
        ('all', 'Allow', {'nsg-allow-all-ingress'}),
        ('all', 'Deny', {'nsg-deny-all-ingress'}),
        ('any', 'Allow', {'nsg-allow-all-ingress', 'nsg-mixed-rules'}),
        ('any', 'Deny', {'nsg-deny-all-ingress', 'nsg-mixed-rules'}),
    ])
    @terraform("nsg_no_cidr_no_ports")
    def test_no_cidr_no_ports(self, match, access, expected_resources):
        p = self.load_policy({
                'name': 'test-azure-nsg',
                'resource': 'azure.networksecuritygroup',
                'filters': [{
                    'type': 'ingress',
                    'match': match,
                    'access': access
                }],
            })
        resources = p.run()
        self.assertEqual({r['name'] for r in resources}, expected_resources)

    @terraform("nsg_no_cidr_no_ports")
    def test_deny_implicit(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'ingress',
                'ports': '20-21',
                'match': 'all',
                'access': 'Deny'}],
        })

        resources = p.run()

        self.assertEqual(
            {r['name'] for r in resources}, {'nsg-mixed-rules', 'nsg-deny-all-ingress'}
        )
        for r in resources:
            matched_rules = {rule['name'] for rule in r['c7n:matched-ingress-security-rules']}
            # The nsg with mixed rules denies these ports implicitly.
            if r['name'] == 'nsg-mixed-rules':
                self.assertEqual(matched_rules, set())
            # The nsg with a deny all rule denies these ports explicitly.
            elif r['name'] == 'nsg-deny-all-ingress':
                self.assertEqual(matched_rules, {'deny-all-ingress'})

    @arm_template('networksecuritygroup-remove-rules.json')
    def test_remove_rules_removes_matched_ingress_rule(self):
        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'c7n-nsg-remove-rules'},
                {'type': 'ingress',
                 'source': '*',
                 'access': 'Allow'}],
            'actions': [
                {'type': 'remove-rules',
                 'ingress': 'matched'}],
        })

        resources = p.run()

        assert len(resources) == 1
        matched = resources[0]['c7n:matched-ingress-security-rules']
        assert [r['name'] for r in matched] == ['allow-all-inbound']

    def run_remove_rules(self, *rules, matched=(), **action):
        """Remove rules from an NSG built from (name, priority, direction) specs.

        `matched` names the rules an ingress/egress filter would have annotated.
        Returns the name of each rule the action asked Azure to delete.
        """
        built = [{
            'name': name,
            'id': '/subscriptions/xxx/securityRules/%s' % name,
            'properties': {
                'protocol': '*',
                'sourcePortRange': '*',
                'destinationPortRange': '*',
                'sourceAddressPrefix': '*',
                'destinationAddressPrefix': '*',
                'access': 'Allow',
                'priority': priority,
                'direction': direction,
            },
        } for name, priority, direction in rules]

        nsg = {
            'name': 'nsg-test',
            'resourceGroup': 'test-rg',
            'properties': {'securityRules': built},
        }
        for key, direction in (('c7n:matched-ingress-security-rules', 'Inbound'),
                               ('c7n:matched-egress-security-rules', 'Outbound')):
            hits = [r for r in built
                    if r['name'] in matched and r['properties']['direction'] == direction]
            if hits:
                nsg[key] = hits

        p = self.load_policy({
            'name': 'test-azure-nsg',
            'resource': 'azure.networksecuritygroup',
            'actions': [dict(type='remove-rules', **action)],
        })
        remove = p.resource_manager.actions[0]
        remove.manager.get_client = MagicMock()
        remove.process([nsg])

        deleted = remove.manager.get_client.return_value.security_rules.begin_delete
        return [call[0][2] for call in deleted.call_args_list]

    def test_remove_rules_deletes_the_matched_rule(self):
        deleted = self.run_remove_rules(
            ('allow-ssh', 100, 'Inbound'),
            ('allow-http', 200, 'Inbound'),
            matched=('allow-ssh',), ingress='matched')

        assert deleted == ['allow-ssh']

    def test_remove_rules_without_a_filter_deletes_nothing(self):
        deleted = self.run_remove_rules(
            ('allow-ssh', 100, 'Inbound'), ingress='matched')

        assert deleted == []

    def test_remove_rules_all_only_touches_one_direction(self):
        deleted = self.run_remove_rules(
            ('in-1', 100, 'Inbound'),
            ('in-2', 200, 'Inbound'),
            ('out-1', 100, 'Outbound'),
            ingress='all')

        assert sorted(deleted) == ['in-1', 'in-2']

    def test_remove_rules_handles_egress(self):
        deleted = self.run_remove_rules(
            ('allow-rdp-out', 100, 'Outbound'),
            matched=('allow-rdp-out',), egress='matched')

        assert deleted == ['allow-rdp-out']


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
