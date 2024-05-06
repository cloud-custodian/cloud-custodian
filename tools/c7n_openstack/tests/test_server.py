# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_openstack import OpenStackTest


class ServerTest(OpenStackTest):

    def test_server_query(self):
        factory = self.replay_flight_data()
        p = self.load_policy({
            'name': 'all-servers',
            'resource': 'openstack.server'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_server_filter_name(self):
        factory = self.replay_flight_data()
        policy = {
            'name': 'get-server-c7n-test-1',
            'resource': 'openstack.server',
            'filters': [
                {
                    "type": "value",
                    "key": "name",
                    "value": "c7n-test-1",
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].name, "c7n-test-1")

    def test_server_filter_flavor(self):
        factory = self.replay_flight_data()
        policy = {
            'name': 'get-server-c7n-test-1',
            'resource': 'openstack.server',
            'filters': [
                {
                    "type": "flavor",
                    "flavor_name": "m1.tiny",
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].name, "c7n-test-1")

    def test_server_filter_tags(self):
        factory = self.replay_flight_data()
        policy = {
            'name': 'get-server-c7n-test-1',
            'resource': 'openstack.server',
            'filters': [
                {
                    "type": "tags",
                    "tags": [
                        {
                            "key": "a",
                            "value": "a",
                        },
                        {
                            "key": "b",
                            "value": "b",
                        },
                    ],
                    "op": "all",
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].name, "c7n-test-2")

    def test_server_filter_securitygroup_open_to_internet(self):
        factory = self.replay_flight_data('test_server_filter_securitygroup_open_to_internet')
        policy = {
            'name': 'get-server-open-to-internet',
            'resource': 'openstack.server',
            'filters': [
                {
                    "type": "security-group",
                    "key": "security_group_rules",
                    "attrs": [
                        {
                            "type": "value",
                            "key": "direction",
                            "value": "ingress"
                        },
                        {
                            "type": "value",
                            "key": "!port_range_min && !port_range_max",
                            "value": True
                        },
                        {
                            "type": "value",
                            "key": "remote_ip_prefix",
                            "value": "0.0.0.0/0"
                        }
                    ]
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].name, "test1")
        self.assertEqual(resources[0]["c7n:ListItemMatches"][0]["direction"], "ingress")
        self.assertIsNone(resources[0]["c7n:ListItemMatches"][0]["port_range_min"])
        self.assertIsNone(resources[0]["c7n:ListItemMatches"][0]["port_range_max"])
        self.assertEqual(resources[0]["c7n:ListItemMatches"][0]["remote_ip_prefix"], "0.0.0.0/0")

    def test_server_filter_securitygroup_stateful(self):
        factory = self.replay_flight_data('test_server_filter_securitygroup_stateful')
        policy = {
            'name': 'get-server-with-stateful-sg',
            'resource': 'openstack.server',
            'filters': [
                {
                    "type": "security-group",
                    "attrs": [
                        {
                            "type": "value",
                            "key": "stateful",
                            "value": True
                        }
                    ]
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertTrue(resources[0]["c7n:ListItemMatches"][0]["stateful"])
        self.assertTrue(resources[1]["c7n:ListItemMatches"][0]["stateful"])
