# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest

from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.resources.elb import ELB, SetSslListenerPolicy


class ELBTagTest(BaseTest):

    def test_elb_tag_and_remove(self):
        self.patch(ELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_elb_tag_and_remove")
        client = session_factory().client("elb")

        policy = self.load_policy(
            {
                "name": "elb-tag",
                "resource": "elb",
                "filters": [{"LoadBalancerName": "CloudCustodian"}],
                "actions": [{"type": "tag", "key": "xyz", "value": "abdef"}],
            },
            config={"account_id": "644160558196"},
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        tags = client.describe_tags(LoadBalancerNames=["CloudCustodian"])[
            "TagDescriptions"
        ][
            0
        ][
            "Tags"
        ]
        tag_map = {t["Key"]: t["Value"] for t in tags}
        self.assertTrue("xyz" in tag_map)

        policy = self.load_policy(
            {
                "name": "elb-tag",
                "resource": "elb",
                "filters": [{"LoadBalancerName": "CloudCustodian"}],
                "actions": [{"type": "remove-tag", "tags": ["xyz"]}],
            },
            config={"account_id": "644160558196"},
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        tags = client.describe_tags(LoadBalancerNames=["CloudCustodian"])[
            "TagDescriptions"
        ][
            0
        ][
            "Tags"
        ]
        tag_map = {t["Key"]: t["Value"] for t in tags}
        self.assertFalse("xyz" in tag_map)

    def test_elb_tags(self):
        self.patch(ELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_elb_tags")
        policy = self.load_policy(
            {
                "name": "elb-mark",
                "resource": "elb",
                "filters": [{"tag:Platform": "ubuntu"}],
            },
            config={"account_id": "644160558196"},
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LoadBalancerName"], "CloudCustodian")

    def test_mark_and_match(self):
        session_factory = self.replay_flight_data("test_elb_mark_and_match")
        policy = self.load_policy(
            {
                "name": "elb-mark",
                "resource": "elb",
                "filters": [{"LoadBalancerName": "CloudCustodian"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "op": "delete",
                        "tag": "custodian_next",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        tags = session_factory().client("elb").describe_tags(
            LoadBalancerNames=["CloudCustodian"]
        )[
            "TagDescriptions"
        ][
            0
        ][
            "Tags"
        ]
        tag_map = {t["Key"]: t["Value"] for t in tags}
        self.assertTrue("custodian_next" in tag_map)

        policy = self.load_policy(
            {
                "name": "elb-mark-filter",
                "resource": "elb",
                "filters": [
                    {"type": "marked-for-op", "tag": "custodian_next", "op": "delete"}
                ],
            },
            config={"account_id": "644160558196"},
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class ELBInstance(BaseTest):

    def test_instance_filter(self):
        session_factory = self.replay_flight_data("test_elb_instance_filter")
        policy = self.load_policy(
            {
                "name": "elb-instance",
                "resource": "elb",
                "filters": [
                    {"type": "instance", "key": "ImageId", "value": "ami-40d28157"}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LoadBalancerName"], "balanced")


class HealthCheckProtocolMismatchTest(BaseTest):

    def test_healthcheck_protocol_mismatch(self):
        session_factory = self.replay_flight_data("test_healthcheck_protocol_mismatch")
        policy = self.load_policy(
            {
                "name": "healthcheck-protocol-mismatch",
                "resource": "elb",
                "filters": [{"type": "healthcheck-protocol-mismatch"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 3)

        # make sure we matched the right load balcners
        elb_names = {elb["LoadBalancerName"] for elb in resources}
        self.assertEqual(
            elb_names,
            {
                "test-elb-no-listeners",
                "test-elb-protocol-matches",
                "test-elb-multiple-listeners",
            },
        )


class SSLPolicyTest(BaseTest):

    def test_ssl_ciphers(self):
        session_factory = self.replay_flight_data("test_ssl_ciphers")
        policy = self.load_policy(
            {
                "name": "test-ssl-ciphers",
                "resource": "elb",
                "filters": [{"type": "ssl-policy", "blacklist": ["Protocol-SSLv2"]}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LoadBalancerName"], "test-elb-invalid-policy")

    def test_set_ssl_listener_policy_fail(self):
        session_factory = self.replay_flight_data("test_set_ssl_listener")
        self.patch(SetSslListenerPolicy, 'process_elb', lambda self, client, elb: elb.xyz)

        policy = self.load_policy({
            "name": "test-set-ssl-listerner",
            "resource": "elb",
            "filters": [{'LoadBalancerName': 'test-elb'}],
            "actions": [{
                "type": "set-ssl-listener-policy",
                "name": "testpolicy",
                "attributes": ["AES128-SHA256", "Protocol-TLSv1"]}]},
            session_factory=session_factory)
        self.assertRaises(AttributeError, policy.run)

    def test_set_ssl_listener_policy(self):
        session_factory = self.replay_flight_data("test_set_ssl_listener")
        client = session_factory().client("elb")
        policy = self.load_policy(
            {
                "name": "test-set-ssl-listerner",
                "resource": "elb",
                "filters": [
                    {
                        "type": "ssl-policy",
                        "blacklist": ["Protocol-SSLv3", "Protocol-TLSv1"],
                    },
                    {
                        "type": "value",
                        "key": "LoadBalancerName",
                        "value": "test-elb",
                        "op": "eq",
                    },
                ],
                "actions": [
                    {
                        "type": "set-ssl-listener-policy",
                        "name": "testpolicy",
                        "attributes": ["Protocol-TLSv1.2", "AES128-SHA256"],
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        response_pol = client.describe_load_balancers(LoadBalancerNames=["test-elb"])
        response_ciphers = client.describe_load_balancer_policies(
            LoadBalancerName="test-elb", PolicyNames=["testpolicy-1493768308000"]
        )
        curr_pol = response_pol["LoadBalancerDescriptions"][0]["ListenerDescriptions"][
            0
        ][
            "PolicyNames"
        ]

        curr_ciphers = []
        for x in response_ciphers["PolicyDescriptions"][0][
            "PolicyAttributeDescriptions"
        ]:
            curr_ciphers.append({str(k): str(v) for k, v in x.items()})
        active_ciphers = [
            x["AttributeName"] for x in curr_ciphers if x["AttributeValue"] == "true"
        ]
        self.assertEqual(
            curr_pol,
            [
                "testpolicy-1493768308000",
            ],
        )
        self.assertEqual(active_ciphers, ["Protocol-TLSv1.2", "AES128-SHA256"])

    def test_set_ssl_listener_policy_predefined(self):
        session_factory = self.replay_flight_data("test_set_ssl_listener_predefined")
        client = session_factory().client("elb")
        policy = self.load_policy(
            {
                "name": "test-set-ssl-listerner",
                "resource": "elb",
                "filters": [
                    {
                        "type": "ssl-policy",
                        "blacklist": ["Protocol-SSLv3", "Protocol-TLSv1", "Protocol-TLSv1.1"],
                    },
                    {
                        "type": "value",
                        "key": "LoadBalancerName",
                        "value": "test-elb",
                        "op": "eq",
                    },
                ],
                "actions": [
                    {
                        "type": "set-ssl-listener-policy",
                        "name": "testpolicy",
                        "attributes": {
                            "Reference-Security-Policy": "ELBSecurityPolicy-TLS-1-2-2017-01"
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        response_pol = client.describe_load_balancers(LoadBalancerNames=["test-elb"])

        response_ciphers = client.describe_load_balancer_policies(
            LoadBalancerName="test-elb", PolicyNames=["testpolicy-1493768308000"]
        )
        curr_pol = response_pol["LoadBalancerDescriptions"][0]["ListenerDescriptions"][
            0
        ][
            "PolicyNames"
        ]

        curr_ciphers = []
        for x in response_ciphers["PolicyDescriptions"][0][
            "PolicyAttributeDescriptions"
        ]:
            curr_ciphers.append({str(k): str(v) for k, v in x.items()})
        active_ciphers = [
            x["AttributeName"] for x in curr_ciphers if x["AttributeValue"] == "true"
        ]
        self.assertEqual(
            curr_pol,
            [
                "testpolicy-1493768308000",
            ],
        )
        self.assertEqual(
            active_ciphers,
            [
                'Protocol-TLSv1.2', 'Server-Defined-Cipher-Order',
                'ECDHE-ECDSA-AES128-GCM-SHA256', 'ECDHE-RSA-AES128-GCM-SHA256',
                'ECDHE-ECDSA-AES128-SHA256', 'ECDHE-RSA-AES128-SHA256',
                'ECDHE-ECDSA-AES256-GCM-SHA384', 'ECDHE-RSA-AES256-GCM-SHA384',
                'ECDHE-ECDSA-AES256-SHA384', 'ECDHE-RSA-AES256-SHA384', 'AES128-GCM-SHA256',
                'AES128-SHA256', 'AES256-GCM-SHA384', 'AES256-SHA256'
            ]
        )

    def test_ssl_matching(self):
        session_factory = self.replay_flight_data("test_ssl_ciphers")
        policy = self.load_policy(
            {
                "name": "test-ssl-matching",
                "resource": "elb",
                "filters": [
                    {
                        "type": "ssl-policy",
                        "matching": "^Protocol-",
                        "whitelist": [
                            "Protocol-TLSv1", "Protocol-TLSv1.1", "Protocol-TLSv1.2"
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LoadBalancerName"], "test-elb-invalid-policy")

    def test_filter_validation_no_blacklist(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "test-ssl-ciphers",
                "resource": "elb",
                "filters": [{"type": "ssl-policy"}],
            },
            session_factory=None,
            validate=False,
        )

    def test_filter_validation_blacklist_not_iterable(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "test-ssl-ciphers",
                "resource": "elb",
                "filters": [{"type": "ssl-policy", "blacklist": "single-value"}],
            },
            session_factory=None,
            validate=False,
        )


class TestDefaultVpc(BaseTest):

    def test_elb_default_vpc(self):
        session_factory = self.replay_flight_data("test_elb_default_vpc")
        p = self.load_policy(
            {
                "name": "elb-default-filters",
                "resource": "elb",
                "filters": [{"type": "default-vpc"}],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LoadBalancerName"], "test-load-balancer")


class TestModifyVpcSecurityGroupsAction(BaseTest):

    def test_elb_remove_security_groups(self):
        # Test conditions:
        #   - running ELB in default VPC
        #   - security group named TEST-PROD-ONLY-SG exists in VPC and is
        #     attached to test ELB
        session_factory = self.replay_flight_data("test_elb_remove_security_groups")
        client = session_factory().client("ec2")
        default_sg_id = client.describe_security_groups(GroupNames=["default"])[
            "SecurityGroups"
        ][
            0
        ][
            "GroupId"
        ]
        p = self.load_policy(
            {
                "name": "elb-modify-security-groups-filter",
                "resource": "elb",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "GroupName",
                        "value": "(.*PROD-ONLY.*)",
                        "op": "regex",
                    }
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "remove": "matched",
                        "isolation-group": default_sg_id,
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        clean_resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["LoadBalancerName"], "test-load-balancer")
        self.assertEqual(len(clean_resources), 0)

    def test_elb_add_security_group(self):
        # Test conditions:
        #   - running one ELB with 'default' VPC security group attached
        #   - security group named TEST-PROD-ONLY-SG exists in VPC and is not
        #     attached to ELB
        session_factory = self.replay_flight_data("test_elb_add_security_group")

        policy = self.load_policy(
            {
                "name": "add-sg-to-prod-elb",
                "resource": "elb",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"},
                    {
                        "type": "value",
                        "key": "LoadBalancerName",
                        "value": "test-load-balancer",
                    },
                ],
                "actions": [{"type": "modify-security-groups", "add": "sg-411b413c"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources[0]["SecurityGroups"]), 1)
        policy.validate()
        after_resources = policy.run()
        self.assertEqual(len(after_resources[0]["SecurityGroups"]), 2)

    def test_elb_add_security_groups(self):
        # Test conditions:
        #   - running one ELB with 'default' VPC security group attached
        #   - security groups named TEST-PROD-ONLY-SG, TEST-SG1, and TEST-SG2
        #     exist in VPC - not attached to ELB

        session_factory = self.replay_flight_data("test_elb_add_security_groups")
        policy = self.load_policy(
            {
                "name": "add-sgs-to-prod-elb",
                "resource": "elb",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"},
                    {
                        "type": "value",
                        "key": "LoadBalancerName",
                        "value": "test-load-balancer",
                    },
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "add": ["sg-411b413c", "sg-8a4b64f7", "sg-5d4a6520"],
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources[0]["SecurityGroups"]), 1)
        policy.validate()
        after_resources = policy.run()
        self.assertEqual(len(after_resources[0]["SecurityGroups"]), 4)

    def test_elb_remove_all_security_groups(self):
        # Test conditions:
        #   - running one ELB with 'default' and 'TEST-PROD-ONLY-SG' VPC
        #     security groups attached
        session_factory = self.replay_flight_data("test_elb_remove_all_security_groups")
        client = session_factory().client("ec2")

        default_sg_id = client.describe_security_groups(GroupNames=["default"])[
            "SecurityGroups"
        ][
            0
        ][
            "GroupId"
        ]

        policy = self.load_policy(
            {
                "name": "add-sg-to-prod-elb",
                "resource": "elb",
                "filters": [
                    {
                        "type": "value",
                        "key": "LoadBalancerName",
                        "value": "test-load-balancer",
                    }
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "remove": "all",
                        "isolation-group": default_sg_id,
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources[0]["SecurityGroups"]), 2)
        policy.validate()
        after_resources = policy.run()
        self.assertEqual(len(after_resources[0]["SecurityGroups"]), 1)
        # Check that it is indeed the isolation group on the ELB
        self.assertEqual(after_resources[0]["SecurityGroups"][0], default_sg_id)


class TestElbLogging(BaseTest):

    def test_enable_s3_logging(self):
        session_factory = self.replay_flight_data("test_elb_enable_s3_logging")
        policy = self.load_policy(
            {
                "name": "test-enable-s3-logging",
                "resource": "elb",
                "filters": [
                    {"type": "value", "key": "LoadBalancerName", "value": "elb1"}
                ],
                "actions": [
                    {
                        "type": "enable-s3-logging",
                        "bucket": "elbv2logtest",
                        "prefix": "elblogs",
                        "emit_interval": 5,
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        client = session_factory().client("elb")
        for elb in resources:
            elb_name = elb["LoadBalancerName"]
            results = client.describe_load_balancer_attributes(
                LoadBalancerName=elb_name
            )
            elb["Attributes"] = results["LoadBalancerAttributes"]

        self.assertEqual(resources[0]["Attributes"]["AccessLog"]["EmitInterval"], 5)
        self.assertEqual(
            resources[0]["Attributes"]["AccessLog"]["S3BucketName"], "elbv2logtest"
        )
        self.assertEqual(
            resources[0]["Attributes"]["AccessLog"]["S3BucketPrefix"], "elblogs"
        )
        self.assertTrue(resources[0]["Attributes"]["AccessLog"]["Enabled"])

    def test_disable_s3_logging(self):
        session_factory = self.replay_flight_data("test_elb_disable_s3_logging")
        policy = self.load_policy(
            {
                "name": "test-disable-s3-logging",
                "resource": "elb",
                "filters": [
                    {"type": "value", "key": "LoadBalancerName", "value": "elb1"}
                ],
                "actions": [{"type": "disable-s3-logging"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        client = session_factory().client("elb")
        for elb in resources:
            elb_name = elb["LoadBalancerName"]
            results = client.describe_load_balancer_attributes(
                LoadBalancerName=elb_name
            )
            elb["Attributes"] = results["LoadBalancerAttributes"]

        self.assertFalse(resources[0]["Attributes"]["AccessLog"]["Enabled"])


class TestElbIsLoggingFilter(BaseTest):
    """ replicate
        - name: elb-is-logging-to-bucket-test
          resource: elb
          filters:
            - type: is-logging
            bucket: elbv2logtest
    """

    def test_is_logging_to_bucket(self):
        session_factory = self.replay_flight_data("test_elb_is_logging_filter")
        policy = self.load_policy(
            {
                "name": "elb-is-logging-to-bucket-test",
                "resource": "elb",
                "filters": [{"type": "is-logging", "bucket": "elbv2logtest"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertGreater(
            len(resources), 0, "Test should find elbs logging " "to elbv2logtest"
        )


class TestElbIsNotLoggingFilter(BaseTest):
    """ replicate
        - name: elb-is-not-logging-to-bucket-test
          resource: elb
          filters:
            - type: is-not-logging
            bucket: otherbucket
    """

    def test_is_logging_to_bucket(self):
        session_factory = self.replay_flight_data("test_elb_is_logging_filter")
        policy = self.load_policy(
            {
                "name": "elb-is-not-logging-to-bucket-test",
                "resource": "elb",
                "filters": [{"type": "is-not-logging", "bucket": "otherbucket"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertGreater(
            len(resources), 0, "Should find elb not logging " "to otherbucket"
        )


class TestElbAttributeFilter(BaseTest):

    def test_is_connection_draining(self):
        """ replicate
            - name: elb-is-connection-draining-test
              resource: elb
              filters:
                - type: attributes
                  key: ConnectionDraining.Enabled
                  value: true
                  op: eq
        """
        session_factory = self.replay_flight_data("test_elb_attribute_filter")
        policy = self.load_policy(
            {
                "name": "elb-is-connection-draining-test",
                "resource": "elb",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "ConnectionDraining.Enabled",
                            "value": True,
                            "op": "eq"
                        }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 1, "Test should find one elb connection draining"
        )

        self.assertEqual(
            resources[0]['Attributes']['ConnectionDraining']['Enabled'], True
        )

    def test_is_not_connection_draining(self):
        """ replicate
            - name: elb-is-not-connection-draining-test
              resource: elb
              filters:
                - type: attributes
                  key: ConnectionDraining.Enabled
                  value: true
                  op: eq
        """
        session_factory = self.replay_flight_data("test_elb_attribute_filter")
        policy = self.load_policy(
            {
                "name": "elb-is-not-connection-draining-test",
                "resource": "elb",
                "filters": [
                    {
                        "type": "attributes",
                        "key": "ConnectionDraining.Enabled",
                        "value": False,
                        "op": "eq"
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 0, "Test should find no elbs without connection draining "
        )

    def test_is_cross_zone_load_balancing(self):
        """ replicate
            - name: elb-is-cross-zone-load-balancing-test
              resource: elb
              filters:
                - type: attributes
                  key: CrossZoneLoadBalancing.Enabled
                  value: true
                  op: eq
        """
        session_factory = self.replay_flight_data("test_elb_attribute_filter")
        policy = self.load_policy(
            {
                "name": "elb-is-cross-zone-load-balancing-test",
                "resource": "elb",
                "filters": [
                    {
                        "type": "attributes",
                        "key": "CrossZoneLoadBalancing.Enabled",
                        "value": True,
                        "op": "eq"
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 1, "Test should find one elb cross zone load balancing"
        )

        self.assertEqual(
            resources[0]['Attributes']['CrossZoneLoadBalancing']['Enabled'], True
        )

    def test_is_not_cross_zone_load_balancing(self):
        """ replicate
            - name: elb-is-not-cross-zone-load-balancing
              resource: elb
              filters:
                - type: attributes
                  key: CrossZoneLoadBalancing.Enabled
                  value: false
                  op: eq
        """
        session_factory = self.replay_flight_data("test_elb_attribute_filter")
        policy = self.load_policy(
            {
                "name": "elb-is-not-cross-zone-load-balancing-test",
                "resource": "elb",
                "filters": [
                    {
                        "type": "attributes",
                        "key": "CrossZoneLoadBalancing.Enabled",
                        "value": False,
                        "op": "eq"
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 0, "Test should find no elbs not cross zone load balancing"
        )

    def test_idle_time_greater_than_30(self):
        """ replicate
            - name: elb-idle-timeout-test
              resource: elb
              filters:
                - type: attributes
                  key: ConnectionSettings.IdleTimeout
                  value: 30
                  op: gt
        """
        session_factory = self.replay_flight_data("test_elb_attribute_filter")
        policy = self.load_policy(
            {
                "name": "elb-idle-timeout-greater-than-30",
                "resource": "elb",
                "filters": [
                    {
                        "type": "attributes",
                        "key": "ConnectionSettings.IdleTimeout",
                        "value": 30,
                        "op": "gt"
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 1, "Test should find 1 elb with idle timeout > 30 seconds"
        )

        self.assertGreater(
            resources[0]['Attributes']['ConnectionSettings']['IdleTimeout'], 30
        )

    def test_idle_time_less_than_30(self):
        """ replicate
            - name: elb-idle-timeout-test
              resource: elb
              filters:
                - type: attributes
                  key: ConnectionSettings.IdleTimeout
                  value: 30
                  op: lt
        """
        session_factory = self.replay_flight_data("test_elb_attribute_filter")
        policy = self.load_policy(
            {
                "name": "elb-idle-timeout-less-than-30",
                "resource": "elb",
                "filters": [
                    {
                        "type": "attributes",
                        "key": "ConnectionSettings.IdleTimeout",
                        "value": 30,
                        "op": "lt"
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 0, "Test should find 0 elbs with idle timeout < 30 seconds"
        )
