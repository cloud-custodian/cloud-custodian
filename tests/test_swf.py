# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestSimpleWorkflowDomain(BaseTest):
    def test_swf_tag_domain(self):
        session_factory = self.replay_flight_data('test_swf_tag_domain')
        p = self.load_policy(
            {
                "name": "test-swf-tag-domain",
                "resource": "swf",
                "filters": [
                    {
                        "type": "value",
                        "key": "name",
                        "op": "eq",
                        "value": "test-custodian-swf",
                    }
                ],
                "actions": [
                    {"type": "tag", "key": "TestTag", "value": "TestValue"}
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_swf_value_filter(self):
        session_factory = self.replay_flight_data('test_swf_value_filter')
        p = self.load_policy(
            {
                "name": "test-swf-value-filter",
                "resource": "swf",
                "filters": [
                    {
                        "type": "value",
                        "key": "name",
                        "op": "eq",
                        "value": "test-custodian-swf",
                    }
                ]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test-custodian-swf')
        self.assertEqual(resources[0]['Tags'][0]['key'], 'TestTag')
        self.assertEqual(resources[0]['Tags'][0]['value'], 'TestValue')
        self.assertEqual(resources[0]['c7n:MatchedFilters'], ['name'])
