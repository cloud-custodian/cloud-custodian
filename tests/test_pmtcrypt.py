# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from .common import BaseTest


class PmtcryptTest(BaseTest):
    def test_tag_action(self):
        session_factory = self.replay_flight_data('test_pmtcrypt_tag_action')
        p = self.load_policy(
            {
                "name": "tag-payment-cryptography",
                "resource": "payment-cryptography-key",
                "actions": [
                    {"type": "tag", "key": "Department", "value": "International"},
                ]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("payment-cryptography")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["KeyArn"])["Tags"]
        self.assertEqual(tags[0]["Value"], "International")

    def test_remove_tag(self):
        session_factory = self.replay_flight_data(
            "test_payment-cryptography_remove_tag"
        )
        p = self.load_policy(
            {
                "name": "remove-tag-payment-cryptography",
                "resource": "payment-cryptography-key",
                "actions": [{"type": "remove-tag", "tags": ["ResourceOwner"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("payment-cryptography")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["KeyArn"])["Tags"]
        self.assertEqual(len(tags), 0)

    def test_delete_(self):
        session_factory = self.replay_flight_data(
            "test_payment-cryptography_delete"
        )
        p = self.load_policy(
            {
                "name": "delete-payment-cryptography",
                "resource": "payment-cryptography-key",
                "filters": [{"tag:Department": "International"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("payment-cryptography")
        key = client.get_key(
            KeyIdentifier=resources[0]["KeyArn"]
        )["Key"]
        self.assertTrue(key["KeyState"], "DELETE_PENDING")
