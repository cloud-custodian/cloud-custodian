# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class NetworkFirewallTest(BaseTest):

    def test_firewall(self):
        factory = self.replay_flight_data("test_network_firewall")
        p = self.load_policy({
            'name': 'firewall-get',
            'resource': 'aws.firewall'},
            session_factory=factory,
            config={'region': 'us-east-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]['FirewallName'] == 'unicron'

    def test_firewall_config(self):
        factory = self.replay_flight_data('test_network_firewall_config')
        p = self.load_policy({
            'name': 'firewall-config',
            'source': 'config',
            'resource': 'aws.firewall'},
            session_factory=factory,
            config={'region': 'us-east-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]['FirewallName'] == 'unicron'
