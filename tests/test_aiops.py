# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class AIOpsInvestigationGroupTest(BaseTest):

    def test_aiops_investigation_group_query(self):
        session_factory = self.replay_flight_data("test_aiops_investigation_group_query")
        p = self.load_policy(
            {
                "name": "aiops-investigation-group-query",
                "resource": "aws.aiops-investigation-group",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        r = resources[0]
        # detail_spec enrichment from get_investigation_group
        self.assertIn("arn", r)
        self.assertIn("name", r)
        self.assertIn("retentionInDays", r)
        self.assertIn("encryptionConfiguration", r)
        self.assertIsInstance(r["Tags"], list)

    def test_aiops_investigation_group_encryption_filter(self):
        session_factory = self.replay_flight_data(
            "test_aiops_investigation_group_encryption_filter"
        )
        p = self.load_policy(
            {
                "name": "aiops-investigation-group-no-cmk",
                "resource": "aws.aiops-investigation-group",
                "filters": [
                    {
                        "type": "value",
                        "key": "encryptionConfiguration.type",
                        "value": "AWS_OWNED_KEY",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["encryptionConfiguration"]["type"], "AWS_OWNED_KEY"
        )

    def test_aiops_investigation_group_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_aiops_investigation_group_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "aiops-investigation-group-tag",
                "resource": "aws.aiops-investigation-group",
                "filters": [{"tag:Env": "absent"}],
                "actions": [{"type": "tag", "key": "Env", "value": "production"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["arn"]

        client = session_factory().client("aiops")
        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertEqual(tags.get("Env"), "production")

        p = self.load_policy(
            {
                "name": "aiops-investigation-group-remove-tag",
                "resource": "aws.aiops-investigation-group",
                "filters": [{"tag:Env": "production"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertNotIn("Env", tags)

    def test_aiops_investigation_group_delete(self):
        session_factory = self.replay_flight_data(
            "test_aiops_investigation_group_delete"
        )
        p = self.load_policy(
            {
                "name": "aiops-investigation-group-delete",
                "resource": "aws.aiops-investigation-group",
                "filters": [{"tag:Owner": "absent"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        deleted_arn = resources[0]["arn"]

        client = session_factory().client("aiops")
        remaining = [
            g["arn"]
            for g in client.list_investigation_groups().get(
                "investigationGroups", []
            )
        ]
        self.assertNotIn(deleted_arn, remaining)
