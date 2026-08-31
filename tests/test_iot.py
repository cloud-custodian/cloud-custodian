# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class IoTThingTest(BaseTest):

    def test_iot_thing_query(self):
        # placebo: iot.ListThings (>=1 thing), tagging GetResources
        factory = self.replay_flight_data("test_iot_thing_query")
        p = self.load_policy(
            {"name": "iot-thing", "resource": "aws.iot"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertTrue(len(resources) >= 1)


class IoTPolicyTest(BaseTest):

    def test_iot_policy_no_wildcard(self):
        # placebo: iot.ListPolicies, iot.GetPolicy - include one policy whose
        # document has an Allow with iot:* or Resource "*", and one scoped.
        factory = self.replay_flight_data("test_iot_policy_no_wildcard")
        p = self.load_policy(
            {
                "name": "iot-policy-wildcard",
                "resource": "aws.iot-policy",
                "filters": [{"type": "no-wildcard"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class IoTCertificateTest(BaseTest):

    def test_iot_certificate_age(self):
        # placebo: iot.ListCertificates, iot.DescribeCertificate - one ACTIVE
        # certificate with creationDate older than 365 days.
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
        # placebo: iot.ListCertificates, iot.DescribeCertificate,
        # iot.UpdateCertificate - one ACTIVE certificate.
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
        # placebo: iot.ListOTAUpdates, iot.GetOTAUpdate - one OTA update whose
        # otaUpdateFiles has a file without a codeSigning block.
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


class IoTLoggingTest(BaseTest):

    def test_iot_logging_disabled(self):
        # placebo: iot.GetV2LoggingOptions - disableAllLogs true or no roleArn.
        factory = self.replay_flight_data("test_iot_logging_disabled")
        p = self.load_policy(
            {
                "name": "iot-logging-disabled",
                "resource": "account",
                "filters": [{"type": "iot-logging"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
