# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_openstack import OpenStackTest


class SecurityGroupTest(OpenStackTest):

    def test_securitygroup_query(self):
        factory = self.replay_flight_data('test_securitygroup_query')
        p = self.load_policy({
            'name': 'all-security-groups',
            'resource': 'openstack.security-group'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_securitygroup_filter_ports(self):
        factory = self.replay_flight_data('test_securitygroup_filter_ports')
        policy = {
            'name': 'get-security-group-test-1',
            'resource': 'openstack.security-group',
            'filters': [
                {
                    "type": "list-item",
                    "key": "security_group_rules",
                    "attrs": [{
                        "type": "value",
                        "key": "port_range_min",
                        "value": None
                    },
                    {
                        "type": "value",
                        "key": "port_range_max",
                        "value": None
                    }]
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_securitygroup_filter_ipaddress(self):
        factory = self.replay_flight_data('test_securitygroup_filter_ipaddress')
        policy = {
            'name': 'get-security-group-test-2',
            'resource': 'openstack.security-group',
            'filters': [
                {
                    "type": "value",
                    "key": "security_group_rules[?direction=='ingress' && "
                           "remote_ip_prefix=='0.0.0.0/0']",
                    "value": 0,
                    "op": "gt",
                    "value_type": "size"
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
