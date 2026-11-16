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

    def test_user_pool_app_client_implicit_grant(self):
        factory = self.replay_flight_data("test_cognito_user_pool_app_client")
        p = self.load_policy(
            {
                "name": "user-pool-client-implicit-grant",
                "resource": "user-pool",
                "filters": [
                    {
                        "type": "app-client",
                        "attrs": [
                            {
                                "type": "value",
                                "key": "AllowedOAuthFlows",
                                "value": "implicit",
                                "op": "contains",
                            }
                        ],
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual([r["Name"] for r in resources], ["c7n-app-client-noncompliant"])
        self.assertEqual(
            [c["ClientName"] for c in resources[0]["c7n:MatchedAppClients"]],
            ["c7n-implicit-password-client"],
        )
        for app_client in resources[0]["c7n:AppClients"]:
            self.assertNotIn("ClientSecret", app_client)
            self.assertIn("c7n:HasClientSecret", app_client)

    def test_user_pool_app_client_password_auth_without_secret(self):
        factory = self.replay_flight_data("test_cognito_user_pool_app_client")
        p = self.load_policy(
            {
                "name": "user-pool-client-password-auth-without-secret",
                "resource": "user-pool",
                "filters": [
                    {
                        "type": "app-client",
                        "attrs": [
                            {
                                "type": "value",
                                "key": "ExplicitAuthFlows",
                                "value": "ALLOW_USER_PASSWORD_AUTH",
                                "op": "contains",
                            },
                            {
                                "type": "value",
                                "key": '"c7n:HasClientSecret"',
                                "value": False,
                            },
                        ],
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual([r["Name"] for r in resources], ["c7n-app-client-noncompliant"])
        self.assertEqual(
            [c["ClientName"] for c in resources[0]["c7n:MatchedAppClients"]],
            ["c7n-implicit-password-client"],
        )

    def test_user_pool_identity_provider_social(self):
        factory = self.replay_flight_data("test_cognito_user_pool_identity_provider")
        p = self.load_policy(
            {
                "name": "user-pool-social-identity-providers",
                "resource": "user-pool",
                "filters": [
                    {
                        "type": "identity-provider",
                        "attrs": [
                            {
                                "type": "value",
                                "key": "ProviderType",
                                "op": "in",
                                "value": [
                                    "Google",
                                    "Facebook",
                                    "LoginWithAmazon",
                                    "SignInWithApple",
                                ],
                            }
                        ],
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual([r["Name"] for r in resources], ["c7n-idp-noncompliant"])
        self.assertEqual(
            [i["ProviderType"] for i in resources[0]["c7n:MatchedIdentityProviders"]],
            ["Google"],
        )
        for provider in resources[0]["c7n:IdentityProviders"]:
            self.assertNotIn("client_secret", provider.get("ProviderDetails", {}))
            self.assertNotIn("private_key", provider.get("ProviderDetails", {}))

    def test_user_pool_log_delivery_missing_auth_events(self):
        factory = self.replay_flight_data("test_cognito_user_pool_log_delivery")
        p = self.load_policy(
            {
                "name": "user-pool-auth-events-not-in-cloudwatch",
                "resource": "user-pool",
                "filters": [
                    {
                        "type": "log-delivery",
                        "count": 0,
                        "attrs": [
                            {"EventSource": "userAuthEvents"},
                            {
                                "type": "value",
                                "key": "CloudWatchLogsConfiguration.LogGroupArn",
                                "value": "present",
                            },
                        ],
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(
            sorted(r["Name"] for r in resources),
            ["c7n-log-delivery-noncompliant", "c7n-log-delivery-noncompliant-other-sources"],
        )
        self.assertEqual(
            {c["EventSource"] for r in resources for c in r["c7n:LogConfigurations"]},
            {"userNotification", "userAuthEvents"},
        )


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
