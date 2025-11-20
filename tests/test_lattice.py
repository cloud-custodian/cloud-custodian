# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class VPCLatticeServiceNetworkTests(BaseTest):

    def test_service_network_cross_account(self):
        """Test cross-account access via auth policy."""
        session_factory = self.replay_flight_data("test_lattice_network_cross_account")
        p = self.load_policy(
            {
                "name": "lattice-find-auth-policy-wildcard",
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
        self.assertIsNotNone(resources)

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

    def test_service_network_has_access_logs(self):
        """Test finding service networks with access logs using ValueFilter syntax."""
        session_factory = self.replay_flight_data("test_lattice_network_both_logs")
        p = self.load_policy(
            {
                "name": "lattice-network-has-logs",
                "resource": "aws.vpc-lattice-service-network",
                "filters": [
                    {
                        "type": "access-logs",
                        "key": "AccessLogSubscriptions",
                        "value_type": "size",
                        "value": 0,
                        "op": "gt"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertTrue(len(resources) > 0,
                        "Should have found at least one resource with access logs")
        self.assertTrue(any(
            r["name"] == "network-with-full-logging" for r in resources
        ), "Expected network-with-full-logging not found")

    def test_service_network_has_s3_logs(self):
        session_factory = self.replay_flight_data("test_lattice_network_both_logs")

        p = self.load_policy(
            {
                "name": "lattice-network-has-s3-logs",
                "resource": "aws.vpc-lattice-service-network",
                "filters": [
                    {
                     "type": "access-logs",
                    "key": "\"AccessLogSubscriptions\"[?contains(destinationArn, 's3')] | [0]",
                    "value": "not-null"
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertTrue(len(resources) > 0,
                        "Should have found at least one resource with S3 logs")
        self.assertTrue(any(
            r["name"] == "network-with-full-logging" for r in resources
        ), "Expected network-with-full-logging not found")


class VPCLatticeServiceTests(BaseTest):

    def test_service_cross_account(self):
        session_factory = self.replay_flight_data("test_lattice_service_cross_account")
        p = self.load_policy(
            {
                "name": "lattice-service-auth-policy-check",
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
        self.assertIsNotNone(resources)

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

    def test_service_has_access_logs(self):
        session_factory = self.replay_flight_data("test_lattice_service_access_logs_enabled")
        p = self.load_policy(
            {
                "name": "lattice-service-has-logs",
                "resource": "aws.vpc-lattice-service",
                "filters": [
                    {
                        "type": "access-logs",
                        "key": "AccessLogSubscriptions",
                        "value": "empty",
                        "op": "ne"
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
        self.assertTrue(found, "Expected service-with-logs not found")

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
