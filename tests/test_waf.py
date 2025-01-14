# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class WAFTest(BaseTest):

    def test_waf_query(self):
        session_factory = self.replay_flight_data("test_waf_query")
        p = self.load_policy(
            {"name": "waftest", "resource": "waf"}, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["WebACLId"], "1ebe0b46-0fd2-4e07-a74c-27bf25adc0bf"
        )
        self.assertEqual(resources[0]["DefaultAction"], {"Type": "BLOCK"})

    def test_wafv2_resolve_resources(self):
        session_factory = self.replay_flight_data(
            "test_wafv2_resolve_resources",
            region="us-east-2"
        )
        p = self.load_policy(
            {"name": "wafv2test", "resource": "aws.wafv2"},
            session_factory=session_factory,
            config={"region": "us-east-2"}
        )
        resources = p.resource_manager.get_resources(["624e04d2-8b45-45ee-b4ad-e853dac6d070"])
        assert len(resources) == 1

    def test_wafv2_logging_configuration(self):
        session_factory = self.replay_flight_data(
            'test_wafv2_logging_configuration')
        policy = {
            'name': 'foo',
            'resource': 'aws.wafv2',
            'filters': [
                {
                    'type': 'logging',
                    'key': 'RedactedFields[].SingleHeader.Name',
                    'value': 'user-agent',
                    'value_type': 'swap',
                    'op': 'in'
                }
            ]
        }
        p = self.load_policy(
            policy,
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:WafV2LoggingConfiguration' in resources[0])
        self.assertEqual(
            resources[0]['c7n:WafV2LoggingConfiguration']['RedactedFields'],
            [
                {
                    'SingleHeader': {
                        'Name': 'user-agent'
                    }
                }
            ]
        )

    def test_wafv2_logging_not_enabled(self):
        session_factory = self.replay_flight_data(
            'test_wafv2_no_logging_configuration')
        policy = {
            'name': 'foo',
            'resource': 'aws.wafv2',
            'filters': [
                {
                    'not': [{
                        'type': 'logging',
                        'key': 'ResourceArn',
                        'value': 'present'
                    }]
                }
            ]
        }
        p = self.load_policy(
            policy,
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:WafV2LoggingConfiguration' not in resources[0])

    def test_wafv2_enable_logging(self):
        session_factory = self.replay_flight_data("test_wafv2_enable_logging")
        policy = {
            "name": "wafv2-enable-logging",
            "resource": "aws.wafv2",
            "filters": [
                {
                    "type": "value",
                    "key": "Name",
                    "value": "test-custodian-waf",
                    "op": "eq"
                }
            ],
            "actions": [
                {
                    "type": "enable-logging",
                    "log_destination_arn": "arn:aws:s3:::aws-waf-logs-test-custodian-creation"
                }
            ]
        }
        p = self.load_policy(policy,
                             session_factory=session_factory,
                             config={"region": "us-east-1"})

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ARN"],
                         "arn:aws:wafv2:us-east-1:644160558196:regional/webacl/test-custodian-waf/48fbb7cc-c08d-4858-900f-a6072fe1a948")

        client = session_factory().client("wafv2")
        logging_config = client.get_logging_configuration(ResourceArn=resources[0]["ARN"])
        self.assertEqual(logging_config["LoggingConfiguration"]["ResourceArn"], resources[0]["ARN"])
        self.assertEqual(logging_config["LoggingConfiguration"]["LogDestinationConfigs"][0],
                         "arn:aws:s3:::aws-waf-logs-test-custodian-creation")

    def test_wafv2_enable_logging_with_redacted_fields(self):
        session_factory = self.replay_flight_data("test_wafv2_enable_logging_with_redacted_fields")
        policy = {
            "name": "wafv2-enable-logging-redacted-fields",
            "resource": "aws.wafv2",
            "filters": [
                {
                    "type": "value",
                    "key": "Name",
                    "value": "test-custodian-waf",
                    "op": "eq"
                }
            ],
            "actions": [
                {
                    "type": "enable-logging",
                    "log_destination_arn": "arn:aws:s3:::aws-waf-logs-test-custodian-creation",
                    "redacted_fields": [
                        {
                            "type": "SingleHeader",
                            "data": "authorization"
                        }
                    ]
                }
            ]
        }
        p = self.load_policy(policy,
                             session_factory=session_factory,
                             config={"region": "us-east-1"})

        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("wafv2")
        logging_config = client.get_logging_configuration(ResourceArn=resources[0]["ARN"])
        self.assertEqual(logging_config["LoggingConfiguration"]["ResourceArn"], resources[0]["ARN"])
        self.assertEqual(logging_config["LoggingConfiguration"]["LogDestinationConfigs"][0],
                         "arn:aws:s3:::aws-waf-logs-test-custodian-creation")
        self.assertIn('RedactedFields', logging_config["LoggingConfiguration"])
        self.assertEqual(
            logging_config["LoggingConfiguration"]["RedactedFields"][0]['SingleHeader']['Name'],
              'authorization')

    # def test_wafv2_enable_logging_invalid_scope(self):
    #     session_factory = self.replay_flight_data("test_wafv2_enable_logging_invalid_scope")
    #     policy = {
    #         "name": "wafv2-enable-logging-invalid-scope",
    #         "resource": "aws.wafv2",
    #         "filters": [
    #             {
    #                 "type": "value",
    #                 "key": "Name",
    #                 "value": "test-custodian-waf",
    #                 "op": "eq"
    #             }
    #         ],
    #         "actions": [
    #             {
    #                 "type": "enable-logging",
    #                 "log_destination_arn": "arn:aws:s3:::aws-waf-logs-test-custodian-creation",
    #                 "log_scope": "INVALID_SCOPE"
    #             }
    #         ]
    #     }
    #     p = self.load_policy(policy,
    #                          session_factory=session_factory,
    #                          config={"region": "us-east-1"})
    #
    #     with self.assertRaises(ValueError) as context:
    #         p.run()
    #     self.assertIn("Invalid log_scope value", str(context.exception))

    def test_wafv2_enable_logging_with_logging_filter(self):
        session_factory = self.replay_flight_data("test_wafv2_enable_logging_with_logging_filter")
        policy = {
            "name": "wafv2-enable-logging-with-filter",
            "resource": "aws.wafv2",
            "filters": [
                {
                    "type": "value",
                    "key": "Name",
                    "value": "test-custodian-waf",
                    "op": "eq"
                }
            ],
            "actions": [
                {
                    "type": "enable-logging",
                    "log_destination_arn": "arn:aws:s3:::aws-waf-logs-test-custodian-creation",
                    "logging_filter": {
                        "Filters": [
                            {
                                "Behavior": "KEEP",
                                "Requirement": "MEETS_ALL",
                                "Conditions": [
                                    {
                                        "ActionCondition": {
                                            "Action": "ALLOW"
                                        }
                                    }
                                ]
                            }
                        ],
                        "DefaultBehavior": "DROP"
                    }
                }
            ]
        }
        p = self.load_policy(policy,
                             session_factory=session_factory,
                             config={"region": "us-east-1"})

        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("wafv2")
        logging_config = client.get_logging_configuration(ResourceArn=resources[0]["ARN"])
        self.assertEqual(logging_config["LoggingConfiguration"]["ResourceArn"], resources[0]["ARN"])
        self.assertEqual(logging_config["LoggingConfiguration"]["LogDestinationConfigs"][0],
                         "arn:aws:s3:::aws-waf-logs-test-custodian-creation")
        self.assertIn('LoggingFilter', logging_config["LoggingConfiguration"])
        self.assertEqual(logging_config["LoggingConfiguration"]["LoggingFilter"]["DefaultBehavior"],
                          "DROP")
