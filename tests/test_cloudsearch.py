# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest


class CloudSearch(BaseTest):

    def test_resource_manager(self):
        factory = self.replay_flight_data("test_cloudsearch_query")
        p = self.load_policy(
            {
                "name": "cs-query",
                "resource": "cloudsearch",
                "filters": [{"DomainName": "sock-index"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "sock-index")

    def test_delete_search(self):
        factory = self.replay_flight_data("test_cloudsearch_delete")
        p = self.load_policy(
            {
                "name": "csdel",
                "resource": "cloudsearch",
                "filters": [{"DomainName": "sock-index"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("cloudsearch")
        state = client.describe_domains(DomainNames=["sock-index"])["DomainStatusList"][
            0
        ]
        self.assertEqual(state["Deleted"], True)
