# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestSimpleWorkflow(BaseTest):
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
        self.assertEqual(resources[0]['c7n:MatchedFilters'], ['name'])
