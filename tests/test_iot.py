# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class IoTThingTest(BaseTest):

    def test_iot_thing_query(self):
        factory = self.replay_flight_data("test_iot_thing_query")
        p = self.load_policy(
            {"name": "iot-thing", "resource": "aws.iot"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertTrue(len(resources) == 1)


class IoTPolicyTest(BaseTest):

    def test_iot_policy_wildcard(self):
        factory = self.replay_flight_data("test_iot_policy_wildcard")
        p = self.load_policy(
            {
                "name": "iot-policy-wildcard",
                "resource": "aws.iot-policy",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Allow",
                                "Action": "iot:*",
                                "PartialMatch": "Action",
                            }
                        ],
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_iot_policy_unattached(self):
        factory = self.replay_flight_data("test_iot_policy_unattached")
        p = self.load_policy(
            {
                "name": "iot-policy-orphaned",
                "resource": "aws.iot-policy",
                "filters": [{"type": "attached", "state": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:Targets"], [])

    def test_iot_policy_delete(self):
        factory = self.replay_flight_data("test_iot_policy_delete")
        p = self.load_policy(
            {
                "name": "iot-policy-delete",
                "resource": "aws.iot-policy",
                "filters": [{"type": "attached", "state": False}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("iot")
        self.assertNotIn(
            resources[0]["policyName"],
            [p["policyName"] for p in client.list_policies()["policies"]])

    def test_iot_policy_tag_untag(self):
        factory = self.replay_flight_data("test_iot_policy_tag_untag")
        p = self.load_policy(
            {
                "name": "iot-policy-tag",
                "resource": "aws.iot-policy",
                "filters": [{"tag:lob": "absent"}],
                "actions": [{"type": "tag", "tags": {"lob": "overhead"}}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("iot")
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]["policyArn"])["tags"]
        self.assertEqual(
            {t["Key"]: t["Value"] for t in tags}, {"lob": "overhead"})

        p = self.load_policy(
            {
                "name": "iot-policy-untag",
                "resource": "aws.iot-policy",
                "filters": [{"tag:lob": "overhead"}],
                "actions": [{"type": "remove-tag", "tags": ["lob"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_resource(
            resourceArn=resources[0]["policyArn"])["tags"]
        self.assertEqual(tags, [])


class IoTCertificateTest(BaseTest):

    def test_iot_certificate_age(self):
        factory = self.replay_flight_data("test_iot_certificate_age")
        p = self.load_policy(
            {
                "name": "iot-cert-age",
                "resource": "aws.iot-certificate",
                "filters": [
                    {"type": "value", "key": "status", "value": "ACTIVE"},
                    {
                        "type": "value",
                        "key": "creationDate",
                        "value_type": "age",
                        "op": "greater-than",
                        "value": 365,
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_iot_certificate_set_inactive(self):
        factory = self.replay_flight_data("test_iot_certificate_set_inactive")
        p = self.load_policy(
            {
                "name": "iot-cert-deactivate",
                "resource": "aws.iot-certificate",
                "filters": [{"type": "value", "key": "status", "value": "ACTIVE"}],
                "actions": [{"type": "set-inactive"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class IoTOTAUpdateTest(BaseTest):

    def test_iot_ota_update_unsigned(self):
        factory = self.replay_flight_data("test_iot_ota_update_unsigned")
        p = self.load_policy(
            {
                "name": "iot-ota-unsigned",
                "resource": "aws.iot-ota-update",
                "filters": [{"type": "unsigned"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_iot_ota_update_tag_untag(self):
        factory = self.replay_flight_data("test_iot_ota_update_tag_untag")
        p = self.load_policy(
            {
                "name": "iot-ota-tag",
                "resource": "aws.iot-ota-update",
                "filters": [{"tag:lob": "absent"}],
                "actions": [{"type": "tag", "tags": {"lob": "overhead"}}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = factory().client("iot")
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]["otaUpdateArn"])["tags"]
        self.assertEqual(
            {t["Key"]: t["Value"] for t in tags}, {"lob": "overhead"})

        p = self.load_policy(
            {
                "name": "iot-ota-untag",
                "resource": "aws.iot-ota-update",
                "filters": [{"tag:lob": "overhead"}],
                "actions": [{"type": "remove-tag", "tags": ["lob"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_resource(
            resourceArn=resources[0]["otaUpdateArn"])["tags"]
        self.assertEqual(tags, [])


class IoTLoggingTest(BaseTest):

    def test_iot_logging_not_configured(self):
        factory = self.replay_flight_data("test_iot_logging_not_configured")
        p = self.load_policy(
            {
                "name": "iot-logging-not-configured",
                "resource": "account",
                "filters": [
                    {
                        "type": "iot-logging",
                        "key": "loggingConfigured",
                        "value": False,
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["c7n:IoTLogging"], {"loggingConfigured": False})

    def test_iot_logging_configured_disabled(self):
        factory = self.replay_flight_data("test_iot_logging_configured_disabled")
        p = self.load_policy(
            {
                "name": "iot-logging-configured-disabled",
                "resource": "account",
                "filters": [
                    {
                        "or": [
                            {
                                "type": "iot-logging",
                                "key": "disableAllLogs",
                                "value": True,
                            },
                            {
                                "type": "iot-logging",
                                "key": "defaultLogLevel",
                                "value": "DISABLED",
                            },
                        ]
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        options = resources[0]["c7n:IoTLogging"]
        self.assertTrue(options["loggingConfigured"])
        self.assertTrue(
            options.get("disableAllLogs")
            or options.get("defaultLogLevel") == "DISABLED")

    def test_iot_logging_configured(self):
        factory = self.replay_flight_data("test_iot_logging_enabled")
        p = self.load_policy(
            {
                "name": "iot-logging-configured",
                "resource": "account",
                "filters": [
                    {
                        "type": "iot-logging",
                        "key": "loggingConfigured",
                        "value": True,
                    },
                    {
                        "type": "iot-logging",
                        "key": "defaultLogLevel",
                        "op": "ne",
                        "value": "DISABLED",
                    },
                    {
                        "type": "iot-logging",
                        "key": "disableAllLogs",
                        "value": False,
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["c7n:IoTLogging"]["loggingConfigured"])
