# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class UserPool(BaseTest):

    def test_query_user_pool(self):
        factory = self.replay_flight_data("test_cognito-user-pool")
        p = self.load_policy(
            {"name": "users", "resource": "user-pool"}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(
            sorted([n["Name"] for n in resources]),
            ["c7nusers", "origin_userpool_MOBILEHUB_1667653900"],
        )
        # Confirm that our augment pass has tag information and detail
        # from describe_user_pool
        self.assertLessEqual({"Id", "Tags", "SchemaAttributes"}, set(resources[0]))

    def test_delete_user_pool(self):
        factory = self.replay_flight_data("test_cognito-user-pool_delete")
        p = self.load_policy(
            {
                "name": "delete-user-pools",
                "resource": "user-pool",
                "filters": [{"Name": "test-delete-user-pool"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "test-delete-user-pool")
        client = factory().client("cognito-idp")
        remainder = client.list_user_pools(MaxResults=10)["UserPools"]
        self.assertEqual(len(remainder), 1)
        self.assertNotEqual(remainder[0]["Name"], "test-delete-user-pool")


class IdentityPool(BaseTest):

    def test_query_identity_pool(self):
        factory = self.replay_flight_data("test_cognito-identity-pool")
        p = self.load_policy(
            {"name": "identities", "resource": "identity-pool"}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(
            sorted([n["IdentityPoolName"] for n in resources]),
            ["origin_MOBILEHUB_1667653900", "test_delete_id_pool"],
        )
        # Confirm that our augment pass has tag information and detail
        # from describe_identity_pool
        self.assertLessEqual(
            {"IdentityPoolId", "Tags", "CognitoIdentityProviders"},
            set(resources[0])
        )

    def test_delete_identity_pool(self):
        factory = self.replay_flight_data("test_cognito-identity-pool_delete")
        p = self.load_policy(
            {
                "name": "delete-identity-pools",
                "resource": "identity-pool",
                "filters": [{"IdentityPoolName": "test_delete_id_pool"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["IdentityPoolName"], "test_delete_id_pool")
        client = factory().client("cognito-identity")
        remainder = client.list_identity_pools(MaxResults=10)["IdentityPools"]
        self.assertEqual(len(remainder), 1)
        self.assertNotEqual(remainder[0]["IdentityPoolName"], "test_delete_id_pool")
