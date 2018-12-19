# Copyright 2016-2017 Capital One Services, LLC
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

import json, time

from .common import BaseTest, functional


class KMSTest(BaseTest):

    def test_kms_grant(self):
        session_factory = self.replay_flight_data("test_kms_grants")
        p = self.load_policy(
            {
                "name": "kms-grant-count",
                "resource": "kms",
                "filters": [{"type": "grant-count"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_key_rotation(self):
        session_factory = self.replay_flight_data("test_key_rotation")
        p = self.load_policy(
            {
                "name": "kms-key-rotation",
                "resource": "kms-key",
                "filters": [
                    {
                        "type": "key-rotation-status",
                        "key": "KeyRotationEnabled",
                        "value": True,
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_set_key_rotation(self):
        session_factory = self.replay_flight_data("test_key_rotation_set")
        p = self.load_policy(
            {
                "name": "enable-key-rotation",
                "resource": "kms-key",
                "filters": [
                    {"tag:Name": "CMK-Rotation-Test"},
                    {
                        "type": "key-rotation-status",
                        "key": "KeyRotationEnabled",
                        "value": False,
                    },
                ],
                "actions": [{"type": "set-rotation", "state": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("kms")
        key = client.get_key_rotation_status(KeyId=resources[0]["KeyId"])
        self.assertEqual(key["KeyRotationEnabled"], True)

    @functional
    def test_kms_remove_matched(self):
        session_factory = self.replay_flight_data("test_kms_remove_matched")

        sts = session_factory().client("sts")
        current_user_arn = sts.get_caller_identity()["Arn"]

        client = session_factory().client("kms")
        key_id = client.create_key()["KeyMetadata"]["KeyId"]
        self.addCleanup(
            client.schedule_key_deletion, KeyId=key_id, PendingWindowInDays=7
        )

        client.put_key_policy(
            KeyId=key_id,
            PolicyName="default",
            Policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "DefaultRoot",
                            "Effect": "Allow",
                            "Principal": {"AWS": current_user_arn},
                            "Action": "kms:*",
                            "Resource": "*",
                        },
                        {
                            "Sid": "SpecificAllow",
                            "Effect": "Allow",
                            "Principal": {"AWS": current_user_arn},
                            "Action": "kms:*",
                            "Resource": "*",
                        },
                        {
                            "Sid": "Public",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "kms:*",
                            "Resource": "*",
                        },
                    ],
                }
            ),
        )

        self.assertStatementIds(
            client, key_id, "DefaultRoot", "SpecificAllow", "Public"
        )

        p = self.load_policy(
            {
                "name": "kms-rm-matched",
                "resource": "kms-key",
                "filters": [
                    {"KeyId": key_id},
                    {"type": "cross-account", "whitelist": [self.account_id]},
                ],
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual([r["KeyId"] for r in resources], [key_id])

        if self.recording:
            time.sleep(60)  # takes time before new policy reflected

        self.assertStatementIds(client, key_id, "DefaultRoot", "SpecificAllow")

    def assertStatementIds(self, client, key_id, *expected):
        p = client.get_key_policy(KeyId=key_id, PolicyName="default")["Policy"]
        actual = [s["Sid"] for s in json.loads(p)["Statement"]]
        self.assertEqual(actual, list(expected))

    @functional
    def test_kms_remove_named(self):
        session_factory = self.replay_flight_data("test_kms_remove_named")
        client = session_factory().client("kms")
        key_id = client.create_key()["KeyMetadata"]["KeyId"]
        self.addCleanup(
            client.schedule_key_deletion, KeyId=key_id, PendingWindowInDays=7
        )

        client.put_key_policy(
            KeyId=key_id,
            PolicyName="default",
            Policy=json.dumps(
                {
                    "Version": "2008-10-17",
                    "Statement": [
                        {
                            "Sid": "DefaultRoot",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "kms:*",
                            "Resource": "*",
                        },
                        {
                            "Sid": "RemoveMe",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "kms:*",
                            "Resource": "*",
                        },
                    ],
                }
            ),
        )

        self.assertStatementIds(client, key_id, "DefaultRoot", "RemoveMe")

        p = self.load_policy(
            {
                "name": "kms-rm-named",
                "resource": "kms-key",
                "filters": [{"KeyId": key_id}],
                "actions": [
                    {"type": "remove-statements", "statement_ids": ["RemoveMe"]}
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(60)  # takes time before new policy reflected

        self.assertStatementIds(client, key_id, "DefaultRoot")


class KMSTagging(BaseTest):

    @functional
    def test_kms_key_tag(self):
        session_factory = self.replay_flight_data("test_kms_key_tag")
        client = session_factory().client("kms")
        key_id = client.create_key()["KeyMetadata"]["KeyId"]
        self.addCleanup(
            client.schedule_key_deletion, KeyId=key_id, PendingWindowInDays=7
        )
        policy = self.load_policy(
            {
                "name": "kms-key-tag",
                "resource": "kms-key",
                "filters": [{"KeyId": key_id}],
                "actions": [
                    {"type": "tag", "key": "RequisiteKey", "value": "Required"}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_resource_tags(KeyId=key_id)["Tags"]
        self.assertEqual(tags[0]["TagKey"], "RequisiteKey")

    @functional
    def test_kms_key_remove_tag(self):
        session_factory = self.replay_flight_data("test_kms_key_remove_tag")
        client = session_factory().client("kms")
        key_id = client.create_key(
            Tags=[{"TagKey": "ExpiredTag", "TagValue": "Invalid"}]
        )[
            "KeyMetadata"
        ][
            "KeyId"
        ]
        self.addCleanup(
            client.schedule_key_deletion, KeyId=key_id, PendingWindowInDays=7
        )

        policy = self.load_policy(
            {
                "name": "kms-key-remove-tag",
                "resource": "kms-key",
                "filters": [{"KeyState": "Enabled"}, {"tag:ExpiredTag": "Invalid"}],
                "actions": [{"type": "remove-tag", "tags": ["ExpiredTag"]}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertTrue(len(resources), 1)
        self.assertEqual(resources[0]["KeyId"], key_id)
        tags = client.list_resource_tags(KeyId=key_id)["Tags"]
        self.assertEqual(len(tags), 0)

    def test_kms_key_related(self):
        session_factory = self.replay_flight_data("test_kms_key_related")
        p = self.load_policy(
            {
                "name": "dms-instance-kms-key-related",
                "resource": 'dms-instance',
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "alias/aws/dms",
                        "op": "eq"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        client = session_factory().client("kms")
        self.assertEqual(len(resources), 1)
        resource_kms_key = resources[0]['KmsKeyId']
        aliases = client.list_aliases(KeyId=resource_kms_key)
        target_key_arn = None
        if aliases['Aliases'][0]['AliasName'] == 'alias/aws/dms':
            target_key_id = aliases['Aliases'][0].get('TargetKeyId')
            target_key_arn = client.describe_key(
                KeyId=target_key_id).get('KeyMetadata').get('Arn')
        self.assertEqual(resources[0]['KmsKeyId'], target_key_arn)
