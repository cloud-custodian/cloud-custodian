# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest

class TestDirectConnectConnection(BaseTest):

    def test_list_direct_connect_connections(self):
        session_factory = self.record_flight_data("test_direct_connect_connections")
        p = self.load_policy(
            {
                "name": "list-direct-connect-connections",
                "resource": "directconnect",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)