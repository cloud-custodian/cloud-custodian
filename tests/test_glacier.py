# Copyright 2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

import json
from .common import BaseTest, functional
from botocore.exceptions import ClientError


class GlacierTagTest(BaseTest):

    @functional
    def test_glacier_tag(self):
        session_factory = self.replay_flight_data("test_glacier_tag")
        client = session_factory().client("glacier")
        name = "c7n-glacier-test"

        client.create_vault(vaultName=name)
        self.addCleanup(client.delete_vault, vaultName=name)

        p = self.load_policy(
            {
                "name": "glacier",
                "resource": "glacier",
                "filters": [
                    {"type": "value", "key": "VaultName", "value": "c7n-glacier-test"}
                ],
                "actions": [{"type": "tag", "key": "abc", "value": "xyz"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VaultName"], name)

        tags = client.list_tags_for_vault(vaultName=resources[0]["VaultName"])
        self.assertEqual(len(tags["Tags"]), 1)
        self.assertTrue("abc" in tags["Tags"])

    def test_glacier_untag(self):
        session_factory = self.replay_flight_data("test_glacier_untag")
        client = session_factory().client("glacier")

        p = self.load_policy(
            {
                "name": "glacier",
                "resource": "glacier",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["abc"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_vault(vaultName=resources[0]["VaultName"])
        self.assertEqual(len(tags["Tags"]), 0)

    def test_glacier_markop(self):
        session_factory = self.replay_flight_data("test_glacier_markop")
        client = session_factory().client("glacier")

        p = self.load_policy(
            {
                "name": "glacier",
                "resource": "glacier",
                "filters": [{"tag:abc": "present"}],
                "actions": [{"type": "mark-for-op", "op": "notify", "days": 4}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_vault(vaultName=resources[0]["VaultName"])
        self.assertEqual(len(tags["Tags"]), 2)
        self.assertTrue("maid_status" in tags["Tags"])


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
