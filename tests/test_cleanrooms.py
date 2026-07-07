# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestCleanRoomsCollaboration(BaseTest):

    def test_collaboration_c3r_no_cleartext(self):
        # Find collaborations that allow cleartext columns
        factory = self.replay_flight_data("test_cleanrooms_collaboration_c3r")
        p = self.load_policy(
            {
                "name": "cleanrooms-c3r",
                "resource": "aws.cleanrooms-collaboration",
                "filters": [
                    {"type": "value",
                     "key": "dataEncryptionMetadata.allowCleartext",
                     "value": True},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["dataEncryptionMetadata"]["allowCleartext"])

    def test_collaboration_c3r_compliant(self):
        factory = self.replay_flight_data("test_cleanrooms_collaboration_c3r_ok")
        p = self.load_policy(
            {
                "name": "cleanrooms-c3r-ok",
                "resource": "aws.cleanrooms-collaboration",
                "filters": [
                    {"type": "value",
                     "key": "dataEncryptionMetadata",
                     "value": "present"},
                    {"type": "value",
                     "key": "dataEncryptionMetadata.allowCleartext",
                     "value": False},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertFalse(resources[0]["dataEncryptionMetadata"]["allowCleartext"])

    def test_collaboration_tag_untag(self):
        factory = self.replay_flight_data("test_cleanrooms_collaboration_tag")
        client = factory().client("cleanrooms")

        p = self.load_policy(
            {
                "name": "cleanrooms-collaboration-tag",
                "resource": "aws.cleanrooms-collaboration",
                "filters": [
                    {"type": "value", "key": "name",
                     "value": "Compliant Collaboration"}],
                "actions": [{"type": "tag", "key": "Env", "value": "Test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["arn"]
        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertEqual(tags.get("Env"), "Test")

        p = self.load_policy(
            {
                "name": "cleanrooms-collaboration-untag",
                "resource": "aws.cleanrooms-collaboration",
                "filters": [{"tag:Env": "Test"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertNotIn("Env", tags)


class TestCleanRoomsMembership(BaseTest):

    def test_membership_query_logging(self):
        factory = self.replay_flight_data("test_cleanrooms_membership_query_logging")
        p = self.load_policy(
            {
                "name": "cleanrooms-query-logging",
                "resource": "aws.cleanrooms-membership",
                "filters": [
                    {"type": "value", "key": "queryLogStatus",
                     "op": "ne", "value": "ENABLED"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertNotEqual(resources[0]["queryLogStatus"], "ENABLED")

    def test_membership_tag_untag(self):
        factory = self.replay_flight_data("test_cleanrooms_membership_tag")
        client = factory().client("cleanrooms")

        p = self.load_policy(
            {
                "name": "cleanrooms-membership-tag",
                "resource": "aws.cleanrooms-membership",
                "filters": [
                    {"type": "value", "key": "collaborationName",
                     "value": "Compliant Collaboration"}],
                "actions": [{"type": "tag", "key": "Env", "value": "Test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["arn"]
        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertEqual(tags.get("Env"), "Test")

        p = self.load_policy(
            {
                "name": "cleanrooms-membership-untag",
                "resource": "aws.cleanrooms-membership",
                "filters": [{"tag:Env": "Test"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertNotIn("Env", tags)


class TestCleanRoomsCollaborationMember(BaseTest):

    def test_member_query_access(self):
        factory = self.replay_flight_data("test_cleanrooms_member_abilities")
        p = self.load_policy(
            {
                "name": "cleanrooms-members-with-query-access",
                "resource": "aws.cleanrooms-collaboration-member",
                "filters": [
                    {"type": "value", "key": "accountId",
                     "op": "not-in", "value": [self.account_id]},
                    {"type": "value", "key": "abilities", "op": "intersect",
                     "value": ["CAN_QUERY", "CAN_RECEIVE_RESULTS"]},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["accountId"], "111111111111")


class TestCleanRoomsConfiguredTable(BaseTest):

    def test_configured_table(self):
        factory = self.replay_flight_data("test_cleanrooms_configured_table")
        p = self.load_policy(
            {
                "name": "cleanrooms-configured-tables",
                "resource": "aws.cleanrooms-configured-table",
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn("tableReference", resources[0])

    def test_configured_table_tag_untag(self):
        factory = self.replay_flight_data("test_cleanrooms_configured_table_tag")
        client = factory().client("cleanrooms")

        p = self.load_policy(
            {
                "name": "cleanrooms-configured-table-tag",
                "resource": "aws.cleanrooms-configured-table",
                "filters": [
                    {"type": "value", "key": "name", "value": "Compliant Table"}],
                "actions": [{"type": "tag", "key": "Env", "value": "Test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["arn"]
        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertEqual(tags.get("Env"), "Test")

        p = self.load_policy(
            {
                "name": "cleanrooms-configured-table-untag",
                "resource": "aws.cleanrooms-configured-table",
                "filters": [{"tag:Env": "Test"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceArn=arn)["tags"]
        self.assertNotIn("Env", tags)
