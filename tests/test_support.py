# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestTrustedAdvisor(BaseTest):
    def test_trusted_advisor_status_filter(self):
        session_factory = self.replay_flight_data('test_trusted_advisor_status_filter')
        p = self.load_policy(
            {
                "name": "test-trusted-advisor-errors",
                "resource": "advisor-check",
                "filters": [
                    {
                        "type": "value",
                        "key": "id",
                        "value": "Hs4Ma3G118"
                    },
                    {
                        "type": "resource-status",
                        "statuses": [
                            "error"
                        ]
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['flaggedResources']), 1 )
        self.assertJmes('[0].flaggedResources[*].status', resources, ["error"])

    def test_trusted_advisor_status_filter_all(self):
        session_factory = self.replay_flight_data('test_trusted_advisor_status_filter_all')
        p = self.load_policy(
            {
                "name": "test-trusted-advisor-all",
                "resource": "advisor-check",
                "filters": [
                    {
                        "type": "value",
                        "key": "id",
                        "value": "Hs4Ma3G118"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['flaggedResources']), 2 )
        self.assertJmes('[0].flaggedResources[*].status', resources, ["error","ok"])

