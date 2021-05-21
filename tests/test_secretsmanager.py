# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestSecretsManager(BaseTest):

    def test_secrets_manager_cross_account(self):
        factory = self.replay_flight_data('test_secrets_manager_cross_account')
        p = self.load_policy({
            'name': 'secrets-manager',
            'resource': 'secrets-manager',
            'filters': ['cross-account']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        secret = resources.pop()
        self.assertEqual(secret['Name'], 'c7n-test-key')
        self.assertEqual(
            secret['CrossAccountViolations'],
            [{'Action': 'secretsmanager:*',
              'Effect': 'Allow',
              'Principal': {'AWS': 'arn:aws:iam::123456789012:root'},
              'Resource': '*'}])

    def test_secrets_manager_tag_resource(self):
        session = self.replay_flight_data("test_secrets_manager_tag")
        client = session(region="us-east-1").client("secretsmanager")
        p = self.load_policy(
            {
                "name": "secrets-manager-resource",
                "resource": "secrets-manager",
                "actions": [{"type": "tag", "key": "new-tag", "value": "new-value"}],
            },
            session_factory=session,
        )
        resources = p.run()
        self.assertFalse(resources[0].get('Tags'))

        p = self.load_policy(
            {
                "name": "secrets-manager-resource",
                "resource": "secrets-manager",
                "actions": [{"type": "remove-tag", "tags": ["new-tag"]}],
            },
            session_factory=session,
        )
        resources = p.run()
        self.assertEqual(resources[0]['Tags'][0]['Key'], 'new-tag')

        final_tags = client.describe_secret(SecretId="c7n-test-key").get("Tags")
        self.assertFalse(final_tags)

    def test_mark_secret_for_op(self):
        session = self.replay_flight_data("test_secrets_manager_mark_for_op")
        client = session(region="us-east-1").client("secretsmanager")
        p = self.load_policy(
            {
                "name": "secrets-manager-resource",
                "resource": "secrets-manager",
                "actions": [{"type": "mark-for-op", "op": "tag", "days": 1}],
            },
            session_factory=session,
        )
        resources = p.run()
        self.assertFalse(resources[0].get('Tags'))
        new_tags = client.describe_secret(SecretId="c7n-test-key").get("Tags")
        self.assertTrue("tag@" in new_tags[0].get("Value"))
