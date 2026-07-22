# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from botocore.exceptions import ClientError

from c7n.resources import dsql

from .common import BaseTest


def _client_error(code):
    return ClientError({'Error': {'Code': code, 'Message': code}}, 'Operation')


class DsqlClusterTest(BaseTest):

    def test_cross_account(self):
        factory = self.replay_flight_data("test_dsql_cluster_cross_account")
        p = self.load_policy(
            {
                "name": "dsql-cross-account",
                "resource": "aws.dsql-cluster",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        for r in resources:
            self.assertIn('c7n:Policy', r)
            self.assertIn('CrossAccountViolations', r)

    def test_tag_and_remove_tag(self):
        factory = self.replay_flight_data("test_dsql_cluster_tag_and_remove_tag")
        tag_policy = self.load_policy(
            {
                "name": "dsql-tag",
                "resource": "aws.dsql-cluster",
                "filters": [{"tag:Env": "absent"}],
                "actions": [{"type": "tag", "tags": {"Env": "prod"}}],
            },
            session_factory=factory,
        )
        tagged = tag_policy.run()
        self.assertTrue(len(tagged) >= 1)

        untag_policy = self.load_policy(
            {
                "name": "dsql-untag",
                "resource": "aws.dsql-cluster",
                "filters": [{"tag:Env": "prod"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        untagged = untag_policy.run()
        self.assertTrue(len(untagged) >= 1)

    def test_delete_force_disables_deletion_protection(self):
        factory = self.replay_flight_data("test_dsql_cluster_delete_force")
        p = self.load_policy(
            {
                "name": "dsql-force-delete",
                "resource": "aws.dsql-cluster",
                "filters": [{"deletionProtectionEnabled": True}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertTrue(len(resources) >= 1)
        client = factory().client('dsql')
        refreshed = client.get_cluster(identifier=resources[0]['identifier'])
        self.assertEqual(refreshed['deletionProtectionEnabled'], False)
        self.assertIn(refreshed['status'], ('DELETING', 'DELETED'))

    def test_cross_account_no_policy(self):
        p = self.load_policy(
            {
                "name": "dsql-cross-account-no-policy",
                "resource": "aws.dsql-cluster",
                "filters": [{"type": "cross-account"}],
            }
        )
        f = p.resource_manager.filters[0]
        client = mock.MagicMock()
        client.get_cluster_policy.side_effect = _client_error('ResourceNotFoundException')
        resource = {'identifier': 'c1', 'arn': 'arn:aws:dsql:us-east-1:1:cluster/c1'}
        with mock.patch.object(dsql, 'local_session') as ls:
            ls.return_value.client.return_value = client
            resources = f.process([resource])
        self.assertIsNone(resource['c7n:Policy'])
        self.assertEqual(resources, [])

    def test_cross_account_error(self):
        p = self.load_policy(
            {
                "name": "dsql-cross-account-error",
                "resource": "aws.dsql-cluster",
                "filters": [{"type": "cross-account"}],
            }
        )
        f = p.resource_manager.filters[0]
        client = mock.MagicMock()
        client.get_cluster_policy.side_effect = _client_error('AccessDeniedException')
        resource = {'identifier': 'c1', 'arn': 'arn:aws:dsql:us-east-1:1:cluster/c1'}
        with mock.patch.object(dsql, 'local_session') as ls:
            ls.return_value.client.return_value = client
            with self.assertRaises(ClientError):
                f.process([resource])

    def test_delete_without_force(self):
        p = self.load_policy(
            {
                "name": "dsql-delete",
                "resource": "aws.dsql-cluster",
                "actions": [{"type": "delete"}],
            }
        )
        action = p.resource_manager.actions[0]
        client = mock.MagicMock()
        resource = {'identifier': 'c1', 'deletionProtectionEnabled': True}
        with mock.patch.object(dsql, 'local_session') as ls:
            ls.return_value.client.return_value = client
            action.process([resource])
        client.update_cluster.assert_not_called()
        client.delete_cluster.assert_called_once_with(identifier='c1')

    def test_delete_missing(self):
        p = self.load_policy(
            {
                "name": "dsql-delete-missing",
                "resource": "aws.dsql-cluster",
                "actions": [{"type": "delete"}],
            }
        )
        action = p.resource_manager.actions[0]
        client = mock.MagicMock()
        client.delete_cluster.side_effect = _client_error('ResourceNotFoundException')
        with mock.patch.object(dsql, 'local_session') as ls:
            ls.return_value.client.return_value = client
            action.process([{'identifier': 'c1'}])
        client.delete_cluster.assert_called_once()

    def test_delete_error(self):
        p = self.load_policy(
            {
                "name": "dsql-delete-error",
                "resource": "aws.dsql-cluster",
                "actions": [{"type": "delete"}],
            }
        )
        action = p.resource_manager.actions[0]
        client = mock.MagicMock()
        client.delete_cluster.side_effect = _client_error('AccessDeniedException')
        with mock.patch.object(dsql, 'local_session') as ls:
            ls.return_value.client.return_value = client
            with self.assertRaises(ClientError):
                action.process([{'identifier': 'c1'}])


class DsqlStreamTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data("test_dsql_stream_query")
        p = self.load_policy(
            {
                "name": "dsql-stream-unordered",
                "resource": "aws.dsql-stream",
                "filters": [
                    {"tag:Name": "c7n-test-stream"},
                    {"ordering": "UNORDERED"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertTrue(len(resources) == 1)
        self.assertTrue(resources[0]['ordering'] == 'UNORDERED')

    def test_delete(self):
        factory = self.replay_flight_data("test_dsql_stream_delete")
        p = self.load_policy(
            {
                "name": "dsql-stream-delete",
                "resource": "aws.dsql-stream",
                "filters": [
                    {"tag:Name": "c7n-test-stream"},
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertTrue(len(resources) == 1)

        client = factory().client('dsql')
        deleted = resources[0]
        refreshed = client.get_stream(
            clusterIdentifier=deleted['clusterIdentifier'],
            streamIdentifier=deleted['streamIdentifier'])
        self.assertIn(refreshed['status'], ('DELETING', 'DELETED'))

    def test_tag_and_remove_tag(self):
        factory = self.replay_flight_data("test_dsql_stream_tag_and_remove_tag")
        tag_policy = self.load_policy(
            {
                "name": "dsql-stream-tag",
                "resource": "aws.dsql-stream",
                "filters": [
                    {"tag:Name": "c7n-test-stream"},
                    {"tag:Env": "absent"},
                ],
                "actions": [{"type": "tag", "tags": {"Env": "prod"}}],
            },
            session_factory=factory,
        )
        tagged = tag_policy.run()
        self.assertTrue(len(tagged) == 1)

        untag_policy = self.load_policy(
            {
                "name": "dsql-stream-untag",
                "resource": "aws.dsql-stream",
                "filters": [
                    {"tag:Name": "c7n-test-stream"},
                    {"tag:Env": "prod"},
                ],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        untagged = untag_policy.run()
        self.assertTrue(len(untagged) >= 1)
