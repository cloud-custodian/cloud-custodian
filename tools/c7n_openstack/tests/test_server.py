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
