# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class VPCLatticeServiceNetworkTests(BaseTest):

    def test_service_network_cross_account_policy(self):
        session_factory = self.replay_flight_data("test_lattice_network_cross_account")
        p = self.load_policy(
            {
                "name": "lattice-find-wildcard-access",
                "resource": "aws.vpc-lattice-service-network",
                "filters": [
                    {
                        "type": "cross-account"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'network-with-external-access')
        self.assertIn("CrossAccountViolations", resources[0])

    def test_service_network_tag_untag(self):
        session_factory = self.replay_flight_data("test_lattice_network_tag_untag")
        p = self.load_policy(
                {
                    "name": "lattice-network-untag-specific",
                    "resource": "aws.vpc-lattice-service-network",
                    "filters": [
                        {"name": "network-with-full-logging"},
                        {"tag:ASV": "PolicyTestASV"}
                    ],
                    "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
                },
                session_factory=session_factory,
            )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_service_network_both_log_types_required(self):
        session_factory = self.replay_flight_data("test_lattice_network_both_logs")
        p = self.load_policy(
            {
                "name": "lattice-network-all-logs-check",
                "resource": "aws.vpc-lattice-service-network",
                "filters": [
                    {
                        "type": "access-logs",
                        "enabled": True,
                        "check_all_types": True
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        found = False
        for r in resources:
            if r["name"] == "network-with-full-logging":
                found = True
                log_types = {sub.get('serviceNetworkLogType')
                             for sub in r.get("c7n:AccessLogSubscriptions", [])}
                self.assertIn('SERVICE', log_types)
                self.assertIn('RESOURCE', log_types)
        self.assertTrue(found, "Expected network-with-full-logging not found")


class VPCLatticeServiceTests(BaseTest):

    def test_service_cross_account_policy(self):
        session_factory = self.replay_flight_data("test_lattice_service_cross_account")
        p = self.load_policy(
            {
                "name": "lattice-service-approved-accounts",
                "resource": "aws.vpc-lattice-service",
                "filters": [
                    {
                        "type": "cross-account",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        found = False
        for r in resources:
            if r["name"] == "service-with-external-access":
                found = True
                self.assertIn("CrossAccountViolations", r)
        self.assertTrue(found, "Expected service-with-external-access not found")

    def test_service_tag_untag(self):
        session_factory = self.replay_flight_data("test_lattice_service_tag_untag")
        p = self.load_policy(
                {
                    "name": "lattice-service-untag-specific",
                    "resource": "aws.vpc-lattice-service",
                    "filters": [
                        {"name": "service-with-logs"},
                        {"tag:ASV": "PolicyTestASV"}
                    ],
                    "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
                },
                session_factory=session_factory,
            )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_service_access_logs_enabled(self):
        session_factory = self.replay_flight_data("test_lattice_service_access_logs_enabled")
        p = self.load_policy(
            {
                "name": "lattice-service-logs-enabled",
                "resource": "aws.vpc-lattice-service",
                "filters": [
                    {"type": "access-logs", "enabled": True}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        found = False
        for r in resources:
            if r["name"] == "service-with-logs":
                found = True
                self.assertGreater(len(r.get("c7n:AccessLogSubscriptions", [])), 0)
        self.assertTrue(found, "Expected service-with-logs not found")

    def test_service_access_logs_destination_type(self):
        session_factory = self.replay_flight_data("test_lattice_service_access_logs_dest")
        p = self.load_policy(
            {
                "name": "lattice-service-logs-to-s3",
                "resource": "aws.vpc-lattice-service",
                "filters": [
                    {
                        "type": "access-logs",
                        "enabled": True,
                        "destination_type": "s3",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        found = False
        for r in resources:
            if r["name"] == "service-with-logs":
                found = True
                self.assertIn("s3", r["c7n:AccessLogSubscriptions"][0]["destinationArn"])
        self.assertTrue(found, "Expected service-with-s3-logs not found")

    def test_service_auth_type_compliant(self):
        session_factory = self.replay_flight_data("test_lattice_service_auth_compliant")
        p = self.load_policy(
            {
                "name": "lattice-service-iam-auth-compliant",
                "resource": "aws.vpc-lattice-service",
                "filters": [
                    {
                        "type": "value",
                        "key": "authType",
                        "value": "AWS_IAM"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        found = False
        for r in resources:
            if r["name"] == "compliant-service":
                found = True
                self.assertEqual(r["authType"], "AWS_IAM")
        self.assertTrue(found, "Expected compliant-service not found")


class VPCLatticeTargetGroupTests(BaseTest):

    def test_target_group_tag_untag(self):
        session_factory = self.replay_flight_data("test_lattice_target_group_tag_untag")
        p = self.load_policy(
            {
                "name": "lattice-target-group-untag",
                "resource": "aws.vpc-lattice-target-group",
                "filters": [
                    {"name": "test-tagging-target-group"},
                    {"tag:ASV": "PolicyTestASV"}
                ],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
