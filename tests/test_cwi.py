# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class CloudWatchInsightRule(BaseTest):

    def test_disable_insight_rule(self):
        factory = self.replay_flight_data("test_insight_rule_disable")
        p = self.load_policy(
            {
                "name": "disable-insight-rule",
                "resource": "insight-rule",
                "filters": [{"Name": "test"}],
                "actions": ["disable"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["State"], "ENABLED")
        client = factory().client("cloudwatch")
        insight_rules = client.describe_insight_rules(MaxResults=10)["InsightRules"]
        self.assertEqual(len(insight_rules), 1)
        self.assertEqual(insight_rules[0]["State"], "DISABLED")

    def test_delete_insight_rule(self):
        factory = self.replay_flight_data("test_insight_rule_delete")
        p = self.load_policy(
            {
                "name": "delete-insight-rule",
                "resource": "insight-rule",
                "filters": [{"Name": "test"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("cloudwatch")
        insight_rules = client.describe_insight_rules(MaxResults=10)["InsightRules"]
        self.assertFalse(insight_rules)
