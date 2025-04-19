from c7n.utils import local_session
from .common import BaseTest


class TestResourceShare(BaseTest):
    def test_resource_share_self_query(self):
        factory = self.replay_flight_data("test_resource_share_self_query")
        policy = self.load_policy(
            {
                "name": "test-resource-share-self",
                "resource": "aws.resource-share-self",
                "actions": [
                    {
                        "type": "tag",
                        "key": "test-key",
                        "value": "test-value",
                    }
                ]
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        policy = self.load_policy(
            {
                "name": "test-resource-share-self",
                "resource": "aws.resource-share-self",
                "filters": [
                    {
                        "tag:test-key": "test-value",
                    },
                ],
                "actions": [
                    {
                        "type": "remove-tag",
                        "tags": ["test-key"],
                    }
                ]
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client("ram")
        share = client.get_resource_shares(
            resourceOwner="SELF",
            resourceShareArns=[resources[0]["resourceShareArn"]],
        )["resourceShares"][0]
        self.assertIsNone(share.get("tags"))

    def test_resource_share_other_query(self):
        factory = self.replay_flight_data("test_resource_share_other_query")
        policy = self.load_policy(
            {
                "name": "test-resource-share-other",
                "resource": "aws.resource-share-other",
                "filters": [
                    {
                        "name": "c7n-test-other-accounts",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_resource_share_disassociate_matched(self):
        factory = self.replay_flight_data("test_resource_share_disassociate_matched")
        policy = self.load_policy(
            {
                "name": "test-resource-share-disassociate",
                "resource": "aws.resource-share-self",
                "filters": [
                    {
                        "type": "external-share",
                        "allowlist_entities": ["210987654321"],
                    },
                ],
                "actions": [
                    {
                        "type": "disassociate",
                        "principals": "matched",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client("ram")
        assoc = client.get_resource_share_associations(
            associationType="PRINCIPAL",
            resourceShareArns=[resources[0]["resourceShareArn"]],
        )["resourceShareAssociations"]
        associated = [a for a in assoc if a["status"] == "ASSOCIATED"]
        self.assertEqual(len(associated), 1)
        self.assertEqual(associated[0]["associatedEntity"], "210987654321")

    def test_resource_share_disassociate_all(self):
        factory = self.replay_flight_data("test_resource_share_disassociate_all")
        policy = self.load_policy(
            {
                "name": "test-resource-share-disassociate",
                "resource": "aws.resource-share-self",
                "filters": [
                    {
                        "name": "c7n-test-self",
                    },
                ],
                "actions": [
                    {
                        "type": "disassociate",
                        "principals": "all",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client("ram")
        assoc = client.get_resource_share_associations(
            associationType="PRINCIPAL",
            resourceShareArns=[resources[0]["resourceShareArn"]],
        )["resourceShareAssociations"]
        associated = [a for a in assoc if a["status"] == "ASSOCIATED"]
        self.assertEqual(len(associated), 0)

        policy = self.load_policy(
            {
                "name": "test-resource-share-disassociate",
                "resource": "aws.resource-share-self",
                "filters": [
                    {
                        "type": "external-share",
                        "allowlist_entities": ["111111111111"],
                    },
                ],
                "actions": [
                    {
                        "type": "disassociate",
                        "principals": "all",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client("ram")
        assoc = client.get_resource_share_associations(
            associationType="PRINCIPAL",
            resourceShareArns=[resources[0]["resourceShareArn"]],
        )["resourceShareAssociations"]
        associated = [a for a in assoc if a["status"] == "ASSOCIATED"]
        self.assertEqual(len(associated), 0)

    def test_resource_share_disassociate_all_no_associations(self):
        factory = self.replay_flight_data("test_resource_share_disassociate_all_no_associations")
        policy = self.load_policy(
            {
                "name": "test-resource-share-disassociate",
                "resource": "aws.resource-share-self",
                "filters": [
                    {
                        "name": "c7n-test-self",
                    },
                ],
                "actions": [
                    {
                        "type": "disassociate",
                        "principals": "all",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client("ram")
        assoc = client.get_resource_share_associations(
            associationType="PRINCIPAL",
            resourceShareArns=[resources[0]["resourceShareArn"]],
        )["resourceShareAssociations"]
        associated = [a for a in assoc if a["status"] == "ASSOCIATED"]
        self.assertEqual(len(associated), 0)

    def test_resource_share_self_delete(self):
        factory = self.replay_flight_data("test_resource_share_self_delete")
        policy = self.load_policy(
            {
                "name": "test-resource-share-self",
                "resource": "aws.resource-share-self",
                "actions": [
                    {
                        "type": "delete",
                },
                ],
            },
            session_factory=factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        client = local_session(factory).client("ram")
        shares = client.get_resource_shares(
            resourceOwner="SELF", resourceShareStatus="ACTIVE")["resourceShares"]
        self.assertEqual(len(shares), 0)
