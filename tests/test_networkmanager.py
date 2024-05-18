# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestNetworkManager(BaseTest):

    def test_list_core_networks(self):
        session_factory = self.replay_flight_data("test_networkmanager_list_core_networks")
        p = self.load_policy(
            {
                "name": "list-core-networks",
                "resource": "networkmanager-core-network",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")
            self.assertTrue(r["CoreNetworkArn"])

    def test_describe_global_networks(self):
        session_factory = self.replay_flight_data("test_networkmanager_describe_global_networks")
        p = self.load_policy(
            {
                "name": "describe_global_networks",
                "resource": "networkmanager-global-network",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")

    def test_describe_specific_global_network(self):
        session_factory = self.replay_flight_data(
            "test_networkmanager_describe_specific_global_network")
        p = self.load_policy(
            {
                "name": "describe_global_networks",
                "resource": "networkmanager-global-network",
                "filters": [
                    {"GlobalNetworkId": "global-network-0f952aba212c3fb47"}
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GlobalNetworkId"], "global-network-0f952aba212c3fb47")

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")

    def test_tag_core_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_tag_core_network")
        p = self.load_policy(
            {
                "name": "tag-core-network",
                "resource": "networkmanager-core-network",
                "filters": [
                    {"tag:Name": "test-cloudwan"}
                ],
            "actions": [{"type": "tag", "key": "Category", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["CoreNetworkArn"])["TagList"]
        self.assertEqual(tags[0]["Value"], "TestValue")

    def test_remove_tag_core_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_remove_tag_core_network")
        p = self.load_policy(
            {
                "name": "untag-core-network",
                "resource": "networkmanager-core-network",
                "filters": [{"tag:Name": "test-cloudwan"}],
                "actions": [{"type": "remove-tag", "tags": ["Category"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["CoreNetworkArn"])["TagList"]
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['Key'], "Name")

    def test_delete_core_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_delete_core_network")
        p = self.load_policy(
            {
                "name": "delete-core-network",
                "resource": "networkmanager-core-network",
                "filters": [
                    {"tag:Name": "test-cloudwan"}
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        core_network = client.get_core_network(CoreNetworkId=resources[0]["CoreNetworkId"])['CoreNetwork']
        self.assertEqual(core_network['State'], "DELETING")
