# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from .common import BaseTest
from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.resources.secretsmanager import SecretsManager
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from freezegun import freeze_time


class TestSecretsManager(BaseTest):

    def test_secrets_manager_cross_account(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
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

    def test_secrets_manager_kms_filter(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_secrets_manager_kms_filter')
        kms = session_factory().client('kms')
        p = self.load_policy(
            {
                'name': 'test-secrets-manager-kms-filter',
                'resource': 'secrets-manager',
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/skunk/trails'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['KmsKeyId'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/skunk/trails')

    def test_secrets_manager_has_statement_filter(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        factory = self.replay_flight_data('test_secrets_manager_has_statement_filter')
        p = self.load_policy(
            {
                'name': 'secrets-manager-has-statement',
                'resource': 'secrets-manager',
                'filters': [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": "secretsmanager:GetSecretValue"
                            }
                        ]
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_secrets_manager_tag_resource(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
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
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
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

    def test_secrets_manager_delete(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_secrets_manager_delete')
        client = session_factory(region="us-east-1").client("secretsmanager")
        p = self.load_policy(
            {
                'name': 'secrets-manager-delete',
                'resource': 'secrets-manager',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Name',
                        'value': 'test1'
                    },
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'recovery_window': 7
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'test1')
        secret_for_del = client.describe_secret(SecretId=resources[0]['ARN'])
        self.assertTrue('DeletedDate' in secret_for_del)

    def test_secrets_manager_set_key(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_secrets_manager_set_encryption_key')
        client = session_factory().client('secretsmanager')
        p = self.load_policy(
            {
                'name': 'secrets-manager-set-key',
                'resource': 'aws.secrets-manager',
                'filters': [{'Name': 'cloud-custodion-test'}],
                'actions': [{'type': 'set-encryption', 'key': 'alias/cloud-custodion-test'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        response = client.describe_secret(SecretId=resources[0]['Name'])
        self.assertEqual(response['KmsKeyId'], 'alias/cloud-custodion-test')

    def test_secretsmanager_remove_matched(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data("test_secretsmanager_remove_matched")
        resource_id = 'arn:aws:secretsmanager:us-east-1:644160558196:secret:test-ZO5wu6'
        client = session_factory().client("secretsmanager")
        client.put_resource_policy(SecretId=resource_id, ResourcePolicy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "SpecificAllow",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::644160558196:user/Peter"
                        },
                        "Action": "secretsmanager:GetSecretValue",
                        "Resource": "*"
                    },
                    {
                        "Sid": "CrossAccount",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::040813553448:user/pratyush"
                        },
                        "Action": "secretsmanager:GetSecretValue",
                        "Resource": "*"
                    }
                ]
            }))
        p = self.load_policy(
            {
                "name": "secrets-manager-rm-matched",
                "resource": "secrets-manager",
                "filters": [{"type": "cross-account"}],
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        data = client.get_resource_policy(SecretId=resource_id)
        access_policy = json.loads(data.get('ResourcePolicy'))
        self.assertEqual(len(access_policy.get('Statement')), 1)
        self.assertEqual([s['Sid'] for s in access_policy.get('Statement')], ["SpecificAllow"])

    def test_secretsmanager_remove_rbp(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data("test_secretsmanager_remove_rbp")
        resource_id = 'arn:aws:secretsmanager:us-east-1:644160558196:secret:test-ZO5wu6'
        client = session_factory().client("secretsmanager")
        client.put_resource_policy(SecretId=resource_id, ResourcePolicy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "CrossAccount",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::040813553448:user/pratyush"
                        },
                        "Action": "secretsmanager:GetSecretValue",
                        "Resource": "*"
                    }
                ]
            }))
        p = self.load_policy(
            {
                "name": "secrets-manager-rm-rbp",
                "resource": "secrets-manager",
                "filters": [{"type": "cross-account"}],
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        data = client.get_resource_policy(SecretId=resource_id)
        self.assertEqual(data.get('ResourcePolicy'), None)

    def test_remove_statements_validation_error(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "secrets-manager-remove-matched",
                "resource": "secrets-manager",
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            }
        )

    def test_secrets_manager_describe(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data("test_secrets_manager_describe")
        p = self.load_policy({
            "name": "list-all-secrets",
            "resource": "aws.secrets-manager",
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2 ,resources)
        self.assertIsInstance(resources[0].get('VersionIdsToStages'), dict)
        self.assertEqual(resources[1].get('VersionIdsToStages'), None)
        self.assertEqual(resources[1]['c7n:DeniedMethods'], ['describe_secret'])

    def test_secrets_manager_replica_access_denied(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_secrets_manager_replica_access_denied')

        # Use MagicMock to simulate region-specific behavior and exception
        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'
        # Setup the client for the primary region
        real_client = session_factory(region="us-east-1").client("secretsmanager")
        # Setup the client for the replica region
        replica_client = MagicMock()
        # Simulate AccessDeniedException for describe_secret in replica region
        replica_client.describe_secret.side_effect = ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "User is not authorized"
                }
            },
            "DescribeSecret"
        )
        # When .client('secretsmanager', region_name='us-west-1') is called, return replica_client

        def client_side_effect(service_name, region_name=None):
            if region_name == "eu-west-1":
                return replica_client
            return real_client
        mock_factory().client.side_effect = client_side_effect

        p = self.load_policy(
            {
                'name': 'secrets-manager-replica-access-denied',
                'resource': 'secrets-manager',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Name',
                        'value': 'c7n'
                    },
                    {
                        'type': 'replica-attribute',
                        'key': 'LastAccessedDate',
                        'op': 'ge',
                        'value': '2023-01-01',
                        'value_type': 'date'
                    },
                ]
            },
            session_factory=mock_factory
        )

        with patch.object(
            p.resource_manager.source.manager, 'log'
        ) as mock_log:
            p.run()
            # Assert that the warning log was called for the replica ClientError
            self.assertTrue(mock_log.warning.called)

    def test_secrets_manager_replica_attribute(self):
        self.patch(SecretsManager, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_secrets_manager_replica_attribute')
        p = self.load_policy(
            {
                'name': 'secrets-manager-unencrypted-delete',
                'resource': 'secrets-manager',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Name',
                        'value': 'c7n'
                    },
                    {
                        'type': 'replica-attribute',
                        'key': 'LastAccessedDate',
                        'op': 'ge',
                        'value': '2023-01-01',
                        'value_type': 'date'
                    },
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n')
        self.assertEqual(len(resources[0].get('ReplicationStatus')), 1)
        self.assertIn('c7n:Replicas', resources[0])
        self.assertTrue(isinstance(resources[0]['c7n:Replicas'], list))
        self.assertEqual(len(resources[0]['c7n:Replicas']), 1)
        self.assertEqual(resources[0]['c7n:Replicas'][0]['Name'], 'c7n')

    @freeze_time("2025-12-01")
    def test_secrets_manager_version_age(self):
        session_factory = self.replay_flight_data('test_secrets_manager_version_age')
        p = self.load_policy(
            {
                'name': 'secrets-version-and-age-filter',
                'resource': 'secrets-manager',
                'filters': [
                    {
                        'type': 'current-version',
                        'key': 'CreatedDate',
                        'op': 'lt',
                        'value': 90,
                        'value_type': 'age'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'test_lambda_secret')
        self.assertIn('c7n:CurrentSecretVersion', resources[0])