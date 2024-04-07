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

    def test_firewall_tag_untag(self):
        session_factory = self.replay_flight_data('test_firewall_tag_untag')
        tag = {'env': 'dev'}
        p = self.load_policy(
            {
                'name': 'firewall-tag-untag',
                'resource': 'firewall',
                'filters': [{
                    'tag:owner': 'policy'
                }],
                'actions': [{
                    'type': 'tag',
                    'tags': tag
                },
                {
                    'type': 'remove-tag',
                    'tags': ['owner']
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        client = session_factory().client("network-firewall")
        firewall = client.describe_firewall(FirewallName=resources[0]['FirewallName'])
        tags = firewall['Firewall'].get('Tags')
        self.assertEqual(1, len(tags))
        new_tag = {}
        new_tag[tags[0]['Key']] = tags[0]['Value']
        self.assertEqual(tag, new_tag)

    def test_firewall_mark_for_op(self):
        session_factory = self.replay_flight_data("test_firewall_mark_for_op")
        p = self.load_policy(
            {
                "name": "firewall-mark",
                "resource": "firewall",
                "filters": [
                    {"tag:owner": "policy"},
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "firewall-marked",
                "resource": "firewall",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "skew": 3,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_firewall_logging(self):
        session_factory = self.replay_flight_data('test_network_firewall_logging')
        p = self.load_policy(
            {
                "name": "firewall-config",
                "resource": "aws.firewall",
                "filters": [
                        {
                            "type": "logging-config",
                            "attrs": [
                            {"LogType": "ALERT"},
                            ]
                        }
                    ],
                },
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]['FirewallName'] == 'test-firewall-1'
        client = session_factory().client("network-firewall")
        logging_config = client \
                .describe_logging_configuration(FirewallName=resources[0]['FirewallName'])
        logDestination = logging_config.get('LoggingConfiguration').get('LogDestinationConfigs')[0]
        self.assertEqual(logDestination['LogType'], 'ALERT')

    def test_delete_firewall(self):
        session_factory = self.replay_flight_data("test_delete_firewall")
        p = self.load_policy(
            {
                "name": "delete-firewall",
                "resource": "firewall",
                "filters": [{"tag:owner": "policy"}],
                "actions": [{
                                "type": "delete",
                                "force": True
                            }],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]["FirewallName"], "test-firewall-2")

    def test_update_firewall_logging(self):
        session_factory = self.replay_flight_data("test_update_firewall_logging")

        p = self.load_policy(
            {
                "name": "update-firewall-logging",
                "resource": "firewall",
                "filters": [{"tag:owner": "policy"}],
                "actions": [
                    {
                        "type": "update-logging-config",
                        "enabled": True,
                        "LoggingConfiguration": {
                            "LogDestinationConfigs": [
                                {
                                    "LogType": "FLOW",
                                    "LogDestinationType": "S3",
                                    "LogDestination": {
                                        "bucketName": "c7n-firewall-logging"
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]["FirewallName"], "test-firewall-1")
        client = session_factory().client("network-firewall")
        logging_config = client \
                .describe_logging_configuration(FirewallName=resources[0]['FirewallName'])
        logDestination = logging_config.get('LoggingConfiguration').get('LogDestinationConfigs')[0]
        self.assertEqual(logDestination['LogType'], 'FLOW')
        self.assertEqual(logDestination['LogDestinationType'], 'S3')
        self.assertEqual(logDestination['LogDestination']['bucketName'], 'c7n-firewall-logging')

    def test_update_firewall_logging_disabled(self):
        session_factory = self.replay_flight_data("test_update_firewall_logging_disabled")

        p = self.load_policy(
            {
                "name": "update-firewall-logging",
                "resource": "firewall",
                "filters": [{"tag:owner": "policy"}],
                "actions": [
                    {
                        "type": "update-logging-config",
                        "enabled": False,
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]["FirewallName"], "test-firewall-2")
        client = session_factory().client("network-firewall")
        logging_config = client \
                .describe_logging_configuration(FirewallName=resources[0]['FirewallName'])
        logDestination = logging_config.get('LoggingConfiguration').get('LogDestinationConfigs')
        self.assertEqual(len(logDestination), 0)

    def test_update_firewall_delete_protection(self):
        session_factory = self.replay_flight_data("test_update_firewall_delete_protection")

        p = self.load_policy(
            {
                "name": "update-firewall-delete-protection",
                "resource": "firewall",
                "filters": [{"tag:owner": "policy"}],
                "actions": [
                    {
                        "type": "update-delete-protection",
                        "state": False,
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]["FirewallName"], "test-firewall-1")
        client = session_factory().client("network-firewall")
        firewall = client \
                .describe_firewall(FirewallName=resources[0]['FirewallName'])
        deleteProtection = firewall.get('Firewall').get('DeleteProtection')
        self.assertEqual(deleteProtection, False)
