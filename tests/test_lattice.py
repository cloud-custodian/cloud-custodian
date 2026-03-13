# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from pytest_terraform import terraform

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
                        "type": "cross-account",
                    },
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
                    {"tag:ASV": "PolicyTestASV"},
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
                        "op": "gt",
                    },
                ],
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
                    "value": "not-null",
                    },
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
                    },
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
                    {"tag:ASV": "PolicyTestASV"},
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
                        "op": "ne",
                    },
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
                        "value": "AWS_IAM",
                    },
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
                    {"tag:ASV": "PolicyTestASV"},
                ],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


@terraform("vpc_lattice_listener")
def test_lattice_listener_query(test, vpc_lattice_listener):
    session_factory = test.replay_flight_data("test_lattice_listener_query")
    listener_name = vpc_lattice_listener["aws_vpclattice_listener.example.name"]
    p = test.load_policy(
        {
            "name": "lattice-listener-query",
            "resource": "aws.vpc-lattice-listener",
            "filters": [
                {
                    "type": "value",
                    "key": "name",
                    "value": listener_name,
                }
            ],
        },
        session_factory=session_factory,
    )
    resources = p.run()
    assert len(resources) == 1
    assert resources[0]["name"] == listener_name


@terraform('lattice_service_network_detailspec',)
def test_lattice_service_network_detailspec(test, lattice_service_network_detailspec):
    session_factory = test.replay_flight_data("test_lattice_service_network_detailspec")
    p = test.load_policy(
        {
            "name": "lattice-find-auth-policy-wildcard",
            "resource": "aws.vpc-lattice-service-network",
            "filters": [
                {
                    "type": "value",
                    "key": "authType",
                    "value": "AWS_IAM",
                },
            ],
        },
        session_factory=session_factory,
    )
    resources = p.run()
    assert len(resources) > 0
    assert resources[0]['name'] == 'test-lattice-network'
    assert resources[0]['authType'] == 'AWS_IAM'
    assert resources[0]['Tags'][0]['Key'] == 'TestServiceNetwork'
    assert resources[0]['Tags'][0]['Value'] == 'TestServiceNetworkValue'


@terraform('lattice_rule_query_service')
def test_lattice_rule_query_service(test, lattice_rule_query_service):
    session_factory = test.replay_flight_data("test_lattice_rule_query_service")
    rule_arn = lattice_rule_query_service["aws_vpclattice_listener_rule.test_rule.arn"]
    service_id = lattice_rule_query_service["aws_vpclattice_service.test_service.id"]
    listener_id = lattice_rule_query_service["aws_vpclattice_listener.test_listener.listener_id"]

    p = test.load_policy(
        {
            "name": "lattice-rule-query",
            "resource": "aws.vpc-lattice-rule",
            "query": [{"serviceIdentifier": service_id}],
            "filters": [{"isDefault": False}],
        },
        session_factory=session_factory,
    )

    resources = p.run()
    assert len(resources) == 1
    assert resources[0]["arn"] == rule_arn
    assert resources[0]["serviceIdentifier"] == service_id
    assert resources[0]["listenerIdentifier"] == listener_id


@terraform('lattice_rule_filter_listener')
def test_lattice_rule_filter_listener(test, lattice_rule_filter_listener):
    session_factory = test.replay_flight_data("test_lattice_rule_filter_listener")
    rule_arn = lattice_rule_filter_listener["aws_vpclattice_listener_rule.test_rule.arn"]
    service_id = lattice_rule_filter_listener["aws_vpclattice_service.test_service.id"]
    listener_id = lattice_rule_filter_listener["aws_vpclattice_listener.test_listener.listener_id"]

    p = test.load_policy(
        {
            "name": "lattice-rule-query",
            "resource": "aws.vpc-lattice-rule",
            "filters": [{"listenerIdentifier": listener_id}, {"isDefault": False}],
        },
        session_factory=session_factory,
    )

    resources = p.run()
    assert len(resources) == 1
    assert resources[0]["arn"] == rule_arn
    assert resources[0]["serviceIdentifier"] == service_id
    assert resources[0]["listenerIdentifier"] == listener_id


@terraform('lattice_rule_query_listener')
def test_lattice_rule_query_listener(test, lattice_rule_query_listener):
    listener_id = lattice_rule_query_listener["aws_vpclattice_listener.test_listener.listener_id"]

    p = test.load_policy(
        {
            "name": "lattice-rule-query",
            "resource": "aws.vpc-lattice-rule",
            "query": [{"listenerIdentifier": listener_id}],
            "filters": [{"isDefault": False}],
        },
    )

    with pytest.raises(ValueError, match='Do not pass listenerId without serviceId in the query'):
        p.run()


@terraform('lattice_rule_query_service_listener')
def test_lattice_rule_query_service_listener(test, lattice_rule_query_service_listener):
    session_factory = test.replay_flight_data("test_lattice_rule_query_service_listener")
    rule_arn = lattice_rule_query_service_listener["aws_vpclattice_listener_rule.test_rule.arn"]
    service_id = lattice_rule_query_service_listener["aws_vpclattice_service.test_service.id"]
    listener_id = lattice_rule_query_service_listener[
        "aws_vpclattice_listener.test_listener.listener_id"]

    p = test.load_policy(
        {
            "name": "lattice-rule-query",
            "resource": "aws.vpc-lattice-rule",
            "query": [
                {"serviceIdentifier": service_id},
                {"listenerIdentifier": listener_id},
                {"foo": "bar"},  # Test warning for ignored query parameter
            ],
            "filters": [{"isDefault": False}],
        },
        session_factory=session_factory,
    )

    log_output = test.capture_logging('custodian.lattice')
    resources = p.run()
    assert len(resources) == 1
    assert resources[0]["arn"] == rule_arn
    assert resources[0]["serviceIdentifier"] == service_id
    assert resources[0]["listenerIdentifier"] == listener_id
    assert log_output.getvalue().strip() == \
        '"foo" is not a supported query parameter for this resource.'


@terraform('lattice_rule_tagging')
def test_lattice_rule_tagging(test, lattice_rule_tagging):
    session_factory = test.replay_flight_data("test_lattice_rule_tagging")
    rule_arn = lattice_rule_tagging["aws_vpclattice_listener_rule.test_rule.arn"]
    service_id = lattice_rule_tagging["aws_vpclattice_service.test_service.id"]
    listener_id = lattice_rule_tagging["aws_vpclattice_listener.test_listener.listener_id"]

    p = test.load_policy(
        {
            "name": "lattice-rule-query",
            "resource": "aws.vpc-lattice-rule",
            "query": [{"serviceIdentifier": service_id}, {"listenerIdentifier": listener_id}],
            "filters": [{"isDefault": False}],
            "actions": [{"type": "tag", "key": "NewKey", "value": "NewValue"}]
        },
        session_factory=session_factory,
    )

    resources = p.run()
    assert len(resources) == 1
    assert resources[0]["arn"] == rule_arn
    assert resources[0]['Tags'] == [{'Key': 'ExistingKey', 'Value': 'ExistingValue'}]

    client = session_factory().client("vpc-lattice")
    tags = client.list_tags_for_resource(resourceArn=rule_arn)["tags"]
    assert tags == {'ExistingKey': 'ExistingValue', 'NewKey': 'NewValue'}
