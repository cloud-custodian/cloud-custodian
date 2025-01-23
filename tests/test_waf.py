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

    def test_wafv2_rule_groups(self):
        session_factory = self.replay_flight_data("test_wafv2_rule_groups")

        policy = {
            "name": "test_wafv2_rule_groups",
            "resource": "aws.wafv2",
            "filters": [
                {
                    "not": [{
                        "type": "web-acl-rules",
                        "key": "Type",
                        "value": "Standalone",
                        "op": "eq"
                    }]
                },
                {
                    "type": "web-acl-rules",
                    "key": "Type",
                    "value": "RuleGroup",
                    "op": "in"
                }
            ],
        }

        p = self.load_policy(policy,
                             session_factory=session_factory,
                             config={"region": "us-east-1"})

        resources = p.run()

        self.assertEqual(len(resources), 1, f"Expected 1 resource, got {len(resources)}")

    def test_wafv2_standalone_rules(self):
        session_factory = self.replay_flight_data("test_wafv2_standalone_rules")

        policy = {
            "name": "test_wafv2_standalone_rules",
            "resource": "aws.wafv2",
            "filters": [{
                "or": [
                    {
                        "and": [
                            {
                                "type": "web-acl-rules",
                                "key": "Type",
                                "value": "Standalone",
                                "op": "eq"
                            }
                        ]
                    }
                ]
            }]
        }

        p = self.load_policy(policy,
                             session_factory=session_factory,
                             config={"region": "us-east-1"})

        resources = p.run()
        self.assertEqual(len(resources), 2, f"Expected 2 resources, got {len(resources)}")
