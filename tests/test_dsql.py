# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest


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
