# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestSimpleWorkflow(BaseTest):
    def test_swf_domain_value_filter(self):
        session_factory = self.replay_flight_data('test_swf_domain_value_filter')
        p = self.load_policy(
            {
                "name": "test-swf-domain-value-filter",
                "resource": "swf-domain",
                "filters": [
                    {
                        "type": "value",
                        "key": "name",
                        "op": "eq",
                        "value": "test-custodian-swf-domain",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test-custodian-swf-domain')
        self.assertEqual(resources[0]['c7n:MatchedFilters'], ['name'])

    def test_swf_domain_tag(self):
        session_factory = self.replay_flight_data('test_swf_domain_tag')
        client = session_factory().client("swf")
        p = self.load_policy(
            {
                "name": "test-swf-domain-tag",
                "resource": "swf-domain",
                "actions": [{
                    "type": "tag",
                    "key": "TestKey",
                    "value": "TestValue"
                }]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        tags = client.list_tags_for_resource(resourceArn=resources[0]["arn"])["tags"]
        self.assertEqual(tags[0]["key"], "TestKey")

        p = self.load_policy(
            {
                "name": "test-swf-domain-untag",
                "resource": "swf-domain",
                "actions": [{
                    "type": "remove-tag",
                    "tags": ["TestKey"]
                }]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        tags = client.list_tags_for_resource(resourceArn=resources[0]["arn"])["tags"]
        self.assertEqual(len(tags), 0)

    def test_swf_domain_config(self):
        session_factory = self.replay_flight_data('test_swf_domain_config')
        p = self.load_policy(
            {
                "name": "test-swf-domain-config",
                "resource": "swf-domain",
                "filters": [{
                    "type": "configuration",
                    "key": "workflowExecutionRetentionPeriodInDays",
                    "op": "eq",
                    "value": "90"
                }]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:configuration"][
                "workflowExecutionRetentionPeriodInDays"], "90")
