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

    def test_graphql_api_filter_wafv2_value(self):
        factory = self.replay_flight_data("test_graphql_api_filter_wafv2_value")

        p = self.load_policy(
            {
                "name": "filter-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{"type": "wafv2-enabled", "key": "Rules", "value": "empty"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        # mock WAF has 1 rule
        self.assertEqual(len(resources), 0)

        p = self.load_policy(
            {
                "name": "filter-graphql-api-wafv2",
                "resource": "graphql-api",
                "filters": [{
                    "type": "wafv2-enabled",
                    "key": "length(Rules[?contains(keys(Statement), 'RateBasedStatement')])",
                    "op": "gte",
                    "value": 1
                }]
            },
            session_factory=factory,
        )
        resources = p.run()
        # mock WAF rule has single RateBasedStatement
        self.assertEqual(len(resources), 1)

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


class TestAppSyncApiCache(BaseTest):
    def test_graphql_api_cache_filter(self):
        factory = self.replay_flight_data(
            "test_graphql_api_cache_filter")

        p = self.load_policy(
            {
                "name": "graphql-api-cache-filter",
                "resource": "graphql-api",
                "filters": [{"type": "api-cache",
                             "key": "apiCachingBehavior",
                             "value": "FULL_REQUEST_CACHING"
                             }],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_appsync_api(self):
        factory = self.replay_flight_data("test_delete_appsync_api")
        p = self.load_policy(
            {
                "name": "appsync-delete",
                "resource": "graphql-api",
                "filters": [{"name": "My AppSync App"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], "My AppSync App")
        client = factory().client("appsync")
        self.assertEqual(client.list_graphql_apis()["graphqlApis"], [])
