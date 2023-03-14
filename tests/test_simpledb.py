# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class SimpleDB(BaseTest):

    def test_delete(self):
        session_factory = self.replay_flight_data("test_simpledb_delete")
        p = self.load_policy(
            {
                "name": "sdb-del",
                "resource": "simpledb",
                "filters": [{"DomainName": "supersuper"}],
                "actions": ["delete"],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "supersuper")
        extant_domains = session_factory().client("sdb").list_domains()["DomainNames"]
        self.assertTrue(resources[0]["DomainName"] not in extant_domains)

    def test_simpledb(self):
        session_factory = self.replay_flight_data("test_simpledb_query")
        p = self.load_policy(
            {"name": "sdbtest", "resource": "simpledb"}, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DomainName"], "devtest")
