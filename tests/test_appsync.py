# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest


class AppSyncWafV2(BaseTest):

    def test_graphql_api_filter_wafv2(self):
        factory = self.replay_flight_data("test_graphql_api_filter_wafv2")
        p = self.load_policy(
            {
                "name": "filter-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "state": True}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        p = self.load_policy(
            {
                "name": "filter-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "state": True,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-.*"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "filter-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "state": False}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "filter-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "state": False,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-.*"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_graphql_api_action_wafv2(self):
        factory = self.replay_flight_data("test_graphql_api_action_wafv2")
        p = self.load_policy(
            {
                "name": "action-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "state": False,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-.*"}],
                "actions": [{"type": "set-wafv2", "state": True,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-.*"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        p = self.load_policy(
            {
                "name": "action-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "state": True,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-.*"}],
                "actions": [{"type": "set-wafv2", "state": False,
                             "force": True}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "action-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "state": True,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-.*"}],
                "actions": [{"type": "set-wafv2", "state": True, "force": True,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-TEST.*"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_graphql_api_action_wafv2_regex_multiple_webacl_match(self):
        factory = self.replay_flight_data(
            "test_graphql_api_action_wafv2_regex_multiple_webacl_match")
        p = self.load_policy(
            {
                "name": "action-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "state": False,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-.*"}],
                "actions": [{"type": "set-wafv2", "state": True,
                             "web-acl": ".*FMManagedWebACLV2-?FMS-.*"}]
            },
            session_factory=factory,
        )
        with self.assertRaises(ValueError) as ctx:
            p.run()
        self.assertIn('matching to none or multiple webacls', str(
            ctx.exception))
