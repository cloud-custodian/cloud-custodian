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
