# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import logging
from .common import BaseTest, functional
from botocore.exceptions import ClientError

from c7n import deprecated


class GlacierTagTest(BaseTest):
    # https://github.com/cloud-custodian/cloud-custodian/issues/10998
    # AWS retired the Glacier vault tagging/listing API surface, so
    # vaults are no longer tag-able and augment() no longer tries to
    # call the now-defunct list_tags_for_vault. The tag/remove-tag/
    # mark-for-op actions stay registered as deprecated no-ops (rather
    # than being removed from the schema) so existing policies still
    # validate and run instead of hard failing at policy-load time.

    def test_glacier_tag_actions_are_deprecated_noop(self):
        session_factory = self.replay_flight_data("test_glacier_tag")
        actions = (
            {"type": "tag", "key": "abc", "value": "xyz"},
            {"type": "remove-tag", "tags": ["abc"]},
            {"type": "mark-for-op", "op": "notify", "days": 4},
        )
        for action in actions:
            p = self.load_policy(
                {
                    "name": "glacier",
                    "resource": "glacier",
                    "filters": [
                        {"type": "value", "key": "VaultName", "value": "c7n-glacier-test"}
                    ],
                    "actions": [action],
                },
                session_factory=session_factory,
            )
            # the action is deprecated, not removed - it's still flagged
            # for `custodian validate` to surface.
            self.assertTrue(
                deprecated.check_deprecations(p.resource_manager.actions[0]))

            log_output = self.capture_logging("custodian.actions", level=logging.WARNING)
            resources = p.run()
            self.assertEqual(len(resources), 1)
            self.assertIn("no-op", log_output.getvalue())
            self.assertIn(action["type"], log_output.getvalue())

    def test_glacier_list_no_tag_augment(self):
        # listing/filtering vaults must not call the retired
        # list_tags_for_vault API, and resources carry no Tags.
        session_factory = self.replay_flight_data("test_glacier_tag")
        p = self.load_policy(
            {
                "name": "glacier",
                "resource": "glacier",
                "filters": [
                    {"type": "value", "key": "VaultName", "value": "c7n-glacier-test"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VaultName"], "c7n-glacier-test")
        self.assertNotIn("Tags", resources[0])


class GlacierStatementTest(BaseTest):

    @functional
    def test_glacier_remove_matched(self):
        session_factory = self.replay_flight_data("test_glacier_remove_matched")
        client = session_factory().client("glacier")
        name = "test-glacier-remove-matched"
        client.create_vault(vaultName=name)
        self.addCleanup(client.delete_vault, vaultName=name)
        vault_arn = client.describe_vault(vaultName=name)["VaultARN"]
        client.set_vault_access_policy(
            vaultName=name,
            policy={
                "Policy": json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "SpecificAllow",
                                "Effect": "Allow",
                                "Principal": {"AWS": "arn:aws:iam::185106417252:root"},
                                "Action": "glacier:AddTagsToVault",
                                "Resource": vault_arn,
                            },
                            {
                                "Sid": "Public",
                                "Effect": "Allow",
                                "Principal": {"AWS": "*"},
                                "Action": "glacier:AddTagsToVault",
                                "Resource": vault_arn,
                            },
                        ],
                    }
                )
            },
        )

        p = self.load_policy(
            {
                "name": "glacier-rm-matched",
                "resource": "glacier",
                "filters": [
                    {"VaultName": name},
                    {"type": "cross-account", "whitelist": ["185106417252"]},
                ],
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual([r["VaultName"] for r in resources], [name])

        data = json.loads(
            client.get_vault_access_policy(vaultName=resources[0]["VaultName"]).get(
                "policy"
            )[
                "Policy"
            ]
        )
        self.assertEqual(
            [s["Sid"] for s in data.get("Statement", ())], ["SpecificAllow"]
        )

    @functional
    def test_glacier_remove_named(self):
        session_factory = self.replay_flight_data("test_glacier_remove_named")
        client = session_factory().client("glacier")
        name = "test-glacier-remove-named"

        client.create_vault(vaultName=name)
        self.addCleanup(client.delete_vault, vaultName=name)
        vault_arn = client.describe_vault(vaultName=name)["VaultARN"]
        client.set_vault_access_policy(
            vaultName=name,
            policy={
                "Policy": json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "WhatIsIt",
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["glacier:DescribeVault"],
                                "Resource": vault_arn,
                            }
                        ],
                    }
                )
            },
        )

        p = self.load_policy(
            {
                "name": "glacier-rm-named",
                "resource": "glacier",
                "filters": [{"VaultName": name}],
                "actions": [
                    {"type": "remove-statements", "statement_ids": ["WhatIsIt"]}
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(
            ClientError,
            client.get_vault_access_policy,
            vaultName=resources[0]["VaultName"],
        )

    @functional
    def test_glacier_remove_statement(self):
        session_factory = self.replay_flight_data("test_glacier_remove_statement")
        client = session_factory().client("glacier")
        name = "test-glacier-remove-statement"

        client.create_vault(vaultName=name)
        self.addCleanup(client.delete_vault, vaultName=name)
        vault_arn = client.describe_vault(vaultName=name)["VaultARN"]
        client.set_vault_access_policy(
            vaultName=name,
            policy={
                "Policy": json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "SpecificAllow",
                                "Effect": "Allow",
                                "Principal": {"AWS": "*"},
                                "Action": "glacier:AddTagsToVault",
                                "Resource": vault_arn,
                            },
                            {
                                "Sid": "RemoveMe",
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["glacier:DescribeVault"],
                                "Resource": vault_arn,
                            },
                        ],
                    }
                )
            },
        )

        p = self.load_policy(
            {
                "name": "glacier-rm-statement",
                "resource": "glacier",
                "filters": [{"VaultName": name}],
                "actions": [
                    {"type": "remove-statements", "statement_ids": ["RemoveMe"]}
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(
            client.get_vault_access_policy(vaultName=resources[0]["VaultName"]).get(
                "policy"
            )[
                "Policy"
            ]
        )
        self.assertTrue("RemoveMe" not in [s["Sid"] for s in data.get("Statement", ())])


class GlacierVaultTest(BaseTest):

    def test_glacier_vault_delete(self):
        session_factory = self.replay_flight_data("test_glacier_vault_delete")
        p = self.load_policy(
            {
                "name": "glacier-vault-delete",
                "resource": "aws.glacier",
                "filters": [{"type": "value", "key": "VaultName", "value": "c7n-test-delete"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glacier")
        with self.assertRaises(ClientError) as e:
            client.describe_vault(vaultName='c7n-test-delete')
        self.assertEqual(e.exception.response['Error']['Code'], 'ResourceNotFoundException')
