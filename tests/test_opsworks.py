# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestOpsworksCM(BaseTest):

    def test_query_CM(self):
        factory = self.replay_flight_data("test_opswork-cm_query")
        p = self.load_policy(
            {"name": "get-opswork-cm", "resource": "opswork-cm"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ServerName"], "test-delete-opswork-cm")

    def test_delete_CM(self):
        factory = self.replay_flight_data("test_opswork-cm_delete")
        p = self.load_policy(
            {
                "name": "delete-opswork-cm",
                "resource": "opswork-cm",
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ServerName"], "test-delete-opswork-cm")
        client = factory().client("opsworkscm")
        remainder = client.describe_servers()["Servers"]
        self.assertEqual(len(remainder), 1)
        self.assertEqual(remainder[0]["Status"], "DELETING")


class TestOpsWorksStack(BaseTest):

    def test_query_opsworks_stacks(self):
        factory = self.replay_flight_data("test_opswork-stack_query")
        p = self.load_policy(
            {"name": "get-opswork-stack", "resource": "opswork-stack"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([r["Name"] for r in resources]),
            ["test-delete-opswork-stack", "test-delete-opswork-stack2"],
        )

    def test_stop_opsworks_stacks(self):
        factory = self.replay_flight_data("test_opswork-stack_stop")
        p = self.load_policy(
            {
                "name": "stop-opswork-stack",
                "resource": "opswork-stack",
                "filters": [{"Name": "test-delete-opswork-stack"}],
                "actions": ["stop"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "test-delete-opswork-stack")
        client = factory().client("opsworks")
        remainder = client.describe_stack_summary(StackId=resources[0]["StackId"])[
            "StackSummary"
        ]
        self.assertEqual(remainder["InstancesCount"]["Stopping"], 1)

    def test_delete_opsworks_stacks(self):
        factory = self.replay_flight_data("test_opswork-stack_delete")
        p = self.load_policy(
            {
                "name": "delete-opswork-stack",
                "resource": "opswork-stack",
                "filters": [{"Name": "test-delete-opswork-stack"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "test-delete-opswork-stack")
        client = factory().client("opsworks")
        remainder = client.describe_stacks()["Stacks"]
        self.assertEqual(len(remainder), 1)
        self.assertNotEqual(remainder[0]["Name"], "test-delete-opswork-stack")
