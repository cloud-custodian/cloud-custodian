# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


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
        session_factory = self.replay_flight_data("test_transfer_server_delete")
        p = self.load_policy(
            {
                "name": "transfer-server-test-delete",
                "resource": "transfer-server",
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TransferUser(BaseTest):

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
        session_factory = self.replay_flight_data("test_transfer_user_delete")
        p = self.load_policy(
            {
                "name": "transfer-user-test-delete",
                "resource": "transfer-user",
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
