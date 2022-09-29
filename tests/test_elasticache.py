# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch
from c7n.resources.elasticache import _cluster_eligible_for_snapshot

from .common import BaseTest


class TestElastiCacheCluster(BaseTest):

    def test_eligibility_snapshot(self):
        # so black box testing, due to use of private interface.

        self.assertTrue(
            _cluster_eligible_for_snapshot(
                {'Engine': 'redis', 'CacheNodeType': 'cache.t2.medium'}))
        self.assertFalse(
            _cluster_eligible_for_snapshot(
                {'Engine': 'redis', 'CacheNodeType': 'cache.t1.medium'}))
        self.assertFalse(
            _cluster_eligible_for_snapshot(
                {'Engine': 'memcached', 'CacheNodeType': 'cache.t2.medium'}))

    def test_elasticache_security_group(self):
        session_factory = self.replay_flight_data("test_elasticache_security_group")
        p = self.load_policy(
            {
                "name": "elasticache-cluster-simple",
                "resource": "cache-cluster",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            sorted([r["CacheClusterId"] for r in resources]),
            ["myec-001", "myec-002", "myec-003"],
        )

    def test_elasticache_cost(self):
        aws_region = 'ap-southeast-2'
        session_factory = self.replay_flight_data('elasticache_cost', region=aws_region)
        policy = self.load_policy(
            {
                "name": "elasticache-cost",
                "resource": "cache-cluster",
                "filters": [{
                    "type": "cost",
                    "quantity": 730,
                }]
            },
            session_factory=session_factory,
            config={'region': aws_region},
        )
        with patch("c7n.filters.cost.Cost.invoke_infracost") as infracost:
            infracost.return_value = {'USD': 0.12,
                'description': '$0.12 per  Enhanced Medium Cache node-hour'
                ' (or partial hour) running Redis',
                'purchaseOption': 'on_demand'}
            resources = policy.run()
        self.assertEqual(len(resources), 2)
        assert resources[0]["c7n:Cost"].items() >= {'USD': 87.6}.items()

    def test_elasticache_subnet_filter(self):
        session_factory = self.replay_flight_data(
            "test_elasticache_subnet_group_filter"
        )
        p = self.load_policy(
            {
                "name": "elasticache-cluster-simple",
                "resource": "cache-cluster",
                "filters": [
                    {"type": "subnet", "key": "MapPublicIpOnLaunch", "value": False}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            sorted([r["CacheClusterId"] for r in resources]),
            ["myec-001", "myec-002", "myec-003"],
        )

    def test_elasticache_cluster_simple(self):
        session_factory = self.replay_flight_data("test_elasticache_cluster_simple")
        p = self.load_policy(
            {"name": "elasticache-cluster-simple", "resource": "cache-cluster"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_elasticache_cluster_simple_filter(self):
        session_factory = self.replay_flight_data("test_elasticache_cluster_simple")
        p = self.load_policy(
            {
                "name": "elasticache-cluster-simple-filter",
                "resource": "cache-cluster",
                "filters": [{"type": "value", "key": "Engine", "value": "redis"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_elasticache_sharded_snapshot_copy_tags(self):
        factory = self.replay_flight_data("test_elasticache_sharded_copy_cluster_tags")
        client = factory().client("elasticache")
        snap_tags = {
            t["Key"]: t["Value"]
            for t in client.list_tags_for_resource(
                ResourceName="arn:aws:elasticache:us-east-2:644160558196:snapshot:zero-bytes"
            )[
                "TagList"
            ]
        }
        self.assertEqual(snap_tags, {"App": "MegaCache"})
        p = self.load_policy(
            {
                "name": "test-copy-cluster-tags",
                "resource": "cache-snapshot",
                "actions": [
                    {
                        "type": "copy-cluster-tags",
                        "tags": ["App", "Env", "Zone", "Color"],
                    }
                ],
            },
            config=dict(region="us-east-2"),
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["SnapshotName"], "zero-bytes")
        arn = p.resource_manager.get_arns(resources)[0]
        snap_tags = {
            t["Key"]: t["Value"]
            for t in client.list_tags_for_resource(ResourceName=arn)["TagList"]
        }
        self.assertEqual(
            snap_tags, {"App": "MegaCache", "Color": "Blue", "Env": "Dev", "Zone": "12"}
        )

    def test_elasticache_snapshot_copy_cluster_tags(self):
        session_factory = self.replay_flight_data("test_elasticache_copy_cluster_tags")
        client = session_factory().client("elasticache")
        results = client.list_tags_for_resource(
            ResourceName="arn:aws:elasticache:us-east-1:644160558196:snapshot:myec-backup"
        )[
            "TagList"
        ]
        tags = {t["Key"]: t["Value"] for t in results}
        self.assertEqual(tags, {})

        policy = self.load_policy(
            {
                "name": "test-copy-cluster-tags",
                "resource": "cache-snapshot",
                "actions": [{"type": "copy-cluster-tags", "tags": ["tagkey"]}],
            },
            config=dict(region="us-east-1"),
            session_factory=session_factory,
        )

        resources = policy.run()
        arn = policy.resource_manager.generate_arn(resources[0]["SnapshotName"])
        results = client.list_tags_for_resource(ResourceName=arn)["TagList"]
        tags = {t["Key"]: t["Value"] for t in results}
        self.assertEqual(tags["tagkey"], "tagval")

    def test_elasticache_cluster_available(self):
        session_factory = self.replay_flight_data("test_elasticache_cluster_available")
        p = self.load_policy(
            {
                "name": "elasticache-cluster-available",
                "resource": "cache-cluster",
                "filters": [
                    {"type": "value", "key": "CacheClusterStatus", "value": "available"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(resources[0]["CacheClusterStatus"], "available")

    def test_elasticache_cluster_mark(self):
        session_factory = self.replay_flight_data("test_elasticache_cluster_mark")
        client = session_factory().client("elasticache")
        p = self.load_policy(
            {
                "name": "elasticache-cluster-mark",
                "resource": "cache-cluster",
                "filters": [{"type": "value", "key": "Engine", "value": "redis"}],
                "actions": [{"type": "mark-for-op", "days": 30, "op": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        arn = p.resource_manager.generate_arn(resources[0]["CacheClusterId"])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("maid_status" in tag_map)

    def test_elasticache_cluster_unmark(self):
        session_factory = self.replay_flight_data("test_elasticache_cluster_unmark")
        client = session_factory().client("elasticache")

        p = self.load_policy(
            {
                "name": "elasticache-cluster-unmark",
                "resource": "cache-cluster",
                "filters": [{"type": "value", "key": "Engine", "value": "redis"}],
                "actions": [{"type": "unmark"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        arn = p.resource_manager.generate_arn(resources[0]["CacheClusterId"])
        self.assertEqual(len(resources), 3)
        tags = client.list_tags_for_resource(ResourceName=arn)
        self.assertFalse("maid_status" in tags)

    def test_elasticache_cluster_delete(self):
        session_factory = self.replay_flight_data("test_elasticache_cluster_delete")
        p = self.load_policy(
            {
                "name": "elasticache-cluster-delete",
                "resource": "cache-cluster",
                "filters": [{"type": "value", "key": "Engine", "value": "redis"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_elasticache_cluster_snapshot(self):
        session_factory = self.replay_flight_data("test_elasticache_cluster_snapshot")
        p = self.load_policy(
            {
                "name": "elasticache-cluster-snapshot",
                "resource": "cache-cluster",
                "actions": [{"type": "snapshot"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)


class TestElastiCacheSubnetGroup(BaseTest):

    def test_elasticache_subnet_group(self):
        session_factory = self.replay_flight_data("test_elasticache_subnet_group")
        p = self.load_policy(
            {"name": "elasticache-subnet-group", "resource": "cache-subnet-group"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestElastiCacheSnapshot(BaseTest):

    def test_elasticache_snapshot(self):
        session_factory = self.replay_flight_data("test_elasticache_snapshot")
        p = self.load_policy(
            {"name": "elasticache-snapshot", "resource": "cache-snapshot"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 4)

    def test_elasticache_snapshot_age_filter(self):
        factory = self.replay_flight_data("test_elasticache_snapshot")
        p = self.load_policy(
            {
                "name": "elasticache-snapshot-age-filter",
                "resource": "cache-snapshot",
                "filters": [{"type": "age", "days": 2, "op": "gt"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 4)

    def test_elasticache_snapshot_mark(self):
        session_factory = self.replay_flight_data("test_elasticache_snapshot_mark")
        client = session_factory().client("elasticache")
        p = self.load_policy(
            {
                "name": "elasticache-snapshot-mark",
                "resource": "cache-snapshot",
                "filters": [
                    {
                        "type": "value",
                        "key": "SnapshotName",
                        "value": "backup-myec-001-2017-06-23",
                    }
                ],
                "actions": [{"type": "mark-for-op", "days": 30, "op": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(resources[0]["SnapshotName"])
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("maid_status" in tag_map)

    def test_elasticache_snapshot_unmark(self):
        session_factory = self.replay_flight_data("test_elasticache_snapshot_unmark")
        client = session_factory().client("elasticache")

        p = self.load_policy(
            {
                "name": "elasticache-snapshot-unmark",
                "resource": "cache-snapshot",
                "filters": [
                    {
                        "type": "value",
                        "key": "SnapshotName",
                        "value": "backup-myec-001-2017-06-23",
                    }
                ],
                "actions": [{"type": "unmark"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        arn = p.resource_manager.generate_arn(resources[0]["SnapshotName"])
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(ResourceName=arn)
        self.assertFalse("maid_status" in tags)

    def test_elasticache_snapshot_delete(self):
        factory = self.replay_flight_data("test_elasticache_snapshot_delete")
        p = self.load_policy(
            {
                "name": "elasticache-snapshot-delete",
                "resource": "cache-snapshot",
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 4)


class TestModifyVpcSecurityGroupsAction(BaseTest):

    def test_elasticache_remove_matched_security_groups(self):
        #
        # Test conditions:
        #    - running 2 Elasticache replication group in default VPC with 3 clusters
        #        - translates to 6 clusters
        #    - a default security group with id 'sg-7a3fcb13' exists
        #    - security group named PROD-ONLY-Test-Security-Group exists in VPC and is attached to
        #      one replication group
        #        - translates to 3 clusters marked non-compliant
        #
        # Results in 6 clusters with default Security Group attached
        session_factory = self.replay_flight_data(
            "test_elasticache_remove_matched_security_groups"
        )
        client = session_factory().client("elasticache", region_name="ca-central-1")

        p = self.load_policy(
            {
                "name": "elasticache-remove-matched-security-groups",
                "resource": "cache-cluster",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "GroupName",
                        "value": "(.*PROD-ONLY.*)",
                        "op": "regex",
                    }
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "remove": "matched",
                        "isolation-group": "sg-7a3fcb13",
                    }
                ],
            },
            session_factory=session_factory,
        )
        clean_p = self.load_policy(
            {
                "name": "elasticache-verifyremove-matched-security-groups",
                "resource": "cache-cluster",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()

        waiter = client.get_waiter("replication_group_available")
        waiter.wait()
        clean_resources = clean_p.run()

        # clusters autoscale across AZs, so they get -001, -002, etc appended
        self.assertIn("sg-test-base", resources[0]["CacheClusterId"])

        self.assertEqual(len(resources), 3)
        self.assertEqual(len(resources[0]["SecurityGroups"]), 1)
        # show that it was indeed a replacement of security groups
        self.assertEqual(len(clean_resources[0]["SecurityGroups"]), 1)
        self.assertEqual(len(clean_resources), 6)

    def test_elasticache_add_security_group(self):
        # Test conditions:
        #   - running Elasticache replication group in default VPC with 3 clusters
        #    - a default security group with id 'sg-7a3fcb13' exists
        #    - security group named PROD-ONLY-Test-Security-Group exists in VPC and is not attached
        #        - translates to 3 clusters marked to get new group attached
        #
        # Results in 3 clusters with default Security Group and PROD-ONLY-Test-Security-Group

        session_factory = self.replay_flight_data("test_elasticache_add_security_group")
        client = session_factory().client("elasticache", region_name="ca-central-1")

        p = self.load_policy(
            {
                "name": "add-sg-to-prod-elasticache",
                "resource": "cache-cluster",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
                "actions": [{"type": "modify-security-groups", "add": "sg-6360920a"}],
            },
            session_factory=session_factory,
        )
        clean_p = self.load_policy(
            {
                "name": "validate-add-sg-to-prod-elasticache",
                "resource": "cache-cluster",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"},
                    {
                        "type": "security-group",
                        "key": "GroupName",
                        "value": "PROD-ONLY-Test-Security-Group",
                    },
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        waiter = client.get_waiter("replication_group_available")
        waiter.wait()
        clean_resources = clean_p.run()

        self.assertEqual(len(resources), 3)
        self.assertIn("sg-test-base", resources[0]["CacheClusterId"])
        self.assertEqual(len(resources[0]["SecurityGroups"]), 1)
        self.assertEqual(len(clean_resources[0]["SecurityGroups"]), 2)
        self.assertEqual(len(clean_resources), 3)


class TestElastiCacheReplicationGroup(BaseTest):

    def test_elasticache_replication_group(self):
        session_factory = self.replay_flight_data("test_elasticache_replication_group")
        p = self.load_policy(
            {"name": "elasticache-rg", "resource": "elasticache-group"},
            session_factory=session_factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ReplicationGroupId'], 'test-c7n-rg')

    def test_elasticache_replication_group_delete(self):
        session_factory = self.replay_flight_data("test_elasticache_replication_group_delete")
        p = self.load_policy(
            {
                "name": "replication-group-enc-delete",
                "resource": "elasticache-group",
                "filters": [{"type": "value", "key": "AtRestEncryptionEnabled", "value": False}],
                "actions": [{"type": "delete", "snapshot": True}],
            },
            session_factory=session_factory,)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ReplicationGroupId'], 'c7n-delete')
        client = session_factory().client("elasticache")
        response = client.describe_replication_groups(ReplicationGroupId='c7n-delete')
        self.assertEqual(response.get('ReplicationGroups')[0].get('Status'), 'deleting')

    def test_elasticache_replication_group_tag(self):
        # the elasticache resource uses the universal_taggable wrapper for the AWS
        # resource tagging API - this test ensures that API works for RGs
        session_factory = self.replay_flight_data(
            "test_elasticache_replication_group_tag")
        p = self.load_policy(
            {
                "name": "tag-ElastiCacheReplicationGroup",
                "resource": "elasticache-group",
                "filters": [{"tag:Tagging": "absent"}],
                "actions": [{"type": "tag", "key": "Tagging", "value": "added"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("elasticache")
        response = client.describe_replication_groups(ReplicationGroupId='c7n-tagging')
        while response.get('ReplicationGroups')[0].get('Status') == 'modifying':
            response = client.describe_replication_groups(ReplicationGroupId='c7n-tagging')
        arn = p.resource_manager.get_arns(resources)[0]
        tags = client.list_tags_for_resource(ResourceName=arn)["TagList"]
        self.assertEqual(tags[0]["Value"], "added")
