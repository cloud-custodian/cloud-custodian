# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
from c7n.executor import MainThreadExecutor
from c7n.resources.transfer import DeleteServer, DeleteUser


class TestTransferServer(BaseTest):

    def test_resources(self):
        session_factory = self.replay_flight_data("test_transfer_server")
        p = self.load_policy(
            {"name": "transfer-server-test-describe", "resource": "transfer-server"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ServerId"], "s-4a6d521483294bd79")
        self.assertEqual(resources[0]["State"], "ONLINE")
        self.assertEqual(resources[0]["SecurityPolicyName"], "TransferSecurityPolicy-2020-06")

    def test_security_group_filter(self):
        session_factory = self.replay_flight_data("test_transfer_server_sg_filter")
        p = self.load_policy(
            {
                "name": "transfer-server-test-sg-filter",
                "resource": "transfer-server",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "GroupName",
                        "value": "default",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_subnet_filter(self):
        session_factory = self.replay_flight_data("test_transfer_server_subnet_filter")
        p = self.load_policy(
            {
                "name": "transfer-server-test-subnet-filter",
                "resource": "transfer-server",
                "filters": [
                    {
                        "type": "subnet",
                        "key": "OwnerId",
                        "value": "644160558196",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_network_location_filter(self):
        session_factory = self.replay_flight_data("test_transfer_server_network_location_filter")
        p = self.load_policy(
            {
                "name": "transfer-server-test-network-location-filter",
                "resource": "transfer-server",
                "filters": [
                    {
                        "type": "network-location",
                        "compare": ["resource", "security-group"],
                        "key": "tag:Application",
                        "match": "equal",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_stop_server(self):
        session_factory = self.replay_flight_data("test_transfer_server_stop")
        p = self.load_policy(
            {
                "name": "transfer-server-test-stop",
                "resource": "transfer-server",
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_start_server(self):
        session_factory = self.replay_flight_data("test_transfer_server_start")
        p = self.load_policy(
            {
                "name": "transfer-server-test-start",
                "resource": "transfer-server",
                "actions": [{"type": "start"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_server(self):
        self.patch(DeleteServer, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_transfer_server_delete",
            region="us-east-2"
        )
        p = self.load_policy(
            {
                "name": "transfer-server-test-delete",
                "resource": "transfer-server",
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
            config={"region": "us-east-2"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)


class TestTransferWebApp(BaseTest):

    def test_web_app_tag(self):
        session_factory = self.replay_flight_data("test_transfer_web_app_tag")
        p = self.load_policy(
            {
                "name": "transfer-web-app-test-tag",
                "resource": "transfer-web-app",
                "actions": [
                    {"type": "tag", "key": "Environment", "value": "Production"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("transfer")
        tags = client.describe_web_app(WebAppId=resources[0]["WebAppId"])["WebApp"]["Tags"]
        self.assertTrue(
            any(t["Key"] == "Environment" and t["Value"] == "Production" for t in tags)
        )

        p = self.load_policy(
            {
                "name": "transfer-web-app-test-untag",
                "resource": "transfer-web-app",
                "actions": [{"type": "remove-tag", "tags": ["Environment"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.describe_web_app(WebAppId=resources[0]["WebAppId"])["WebApp"]["Tags"]
        self.assertFalse(
            any(t["Key"] == "Environment" and t["Value"] == "Production" for t in tags)
        )

    def test_delete_web_app(self):
        session_factory = self.replay_flight_data("test_transfer_web_app_delete")
        p = self.load_policy(
            {
                "name": "transfer-web-app-test-delete",
                "resource": "transfer-web-app",
                "filters": [
                    {"type": "value",
                     "key": "WebAppEndpointPolicy",
                     "op": "eq", "value": "STANDARD"}
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("transfer")
        with self.assertRaises(client.exceptions.ResourceNotFoundException):
            client.describe_web_app(WebAppId=resources[0]["WebAppId"])


class TestTransferUser(BaseTest):

    def test_resources(self):
        session_factory = self.replay_flight_data("test_transfer_user")
        p = self.load_policy(
            {"name": "transfer-user-test-describe", "resource": "transfer-user"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["UserName"], "test")

    def test_delete_user(self):
        self.patch(DeleteUser, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_transfer_user_delete",
            region="us-east-2"
        )
        p = self.load_policy(
            {
                "name": "transfer-user-test-delete",
                "resource": "transfer-user",
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
            config={"region": "us-east-2"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
