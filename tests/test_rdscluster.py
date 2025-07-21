# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import sys
from unittest.mock import patch

import c7n.resources.rdscluster
import pytest
from c7n.executor import MainThreadExecutor
from c7n.resources.rdscluster import RDSCluster, _run_cluster_method
from c7n.testing import mock_datetime_now
from dateutil import parser
import c7n.filters.backup

from .common import BaseTest, event_data


class RDSClusterTest(BaseTest):

    def remove_augments(self):
        # This exists because we added tag augmentation after eight other tests
        # were created and I did not want to re-create the state to re-record
        # them with the extra API call. If those get re-recorded we can remove
        # this. -scotwk
        self.patch(RDSCluster, "augment", lambda x, y: y)

    def test_net_location_invalid_subnet(self):
        self.remove_augments()
        session_factory = self.replay_flight_data("test_rdscluster_location_invalid_sub")
        p = self.load_policy({
            'name': 'rds',
            'resource': 'aws.rds-cluster',
            'filters': [
                {'type': 'network-location',
                 'key': 'tag:foobar',
                 'match': 'equal',
                 'compare': ['subnet']}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @pytest.mark.skipif(
        (sys.version_info.major, sys.version_info.minor) < (3, 7) or sys.platform != 'linux',
        reason="needs py 3.8")
    def test_rdscluster_config(self):
        factory = self.replay_flight_data('test_rdscluster_config')
        p = self.load_policy(
            {'name': 'foo', 'resource': 'aws.rds-cluster'},
            session_factory=factory)
        source = p.resource_manager.get_source('config')
        describe_resource = p.resource_manager.get_resources(['database-1'])[0]
        config_resource = source.load_resource(
            event_data('rds-cluster.json', 'config')['configurationItems'][0])

        assert {t['Key']: t['Value'] for t in config_resource['Tags']} == {
            t['Key']: t['Value'] for t in describe_resource['Tags']}

        known_keys = (
            'ClusterCreateTime', 'CustomEndpoints', 'DBClusterOptionGroupMemberships',
            'EnabledCloudwatchLogsExports', 'LatestRestorableTime',
            'EarliestRestorableTime', 'Tags')
        for kk in known_keys:
            config_resource.pop(kk, None)
            describe_resource.pop(kk, None)

        assert describe_resource == config_resource

    def test_rdscluster_api_filter_limit(self):
        self.remove_augments()
        factory = self.replay_flight_data("test_rdscluster_api_filter_limit")
        p = self.load_policy(
            {"name": "foo", "resource": "aws.rds-cluster"},
            session_factory=factory)
        resource_ids = [f"db-instance{i}" for i in range(200)]
        with patch.object(
            p.resource_manager.source.query,
            "filter",
            wraps=p.resource_manager.source.query.filter
        ) as wrapped_filter:
            p.resource_manager.get_resources(resource_ids)
            # 200 unique IDs, batched into chunks of 100
            assert wrapped_filter.call_count == 2

    def test_rdscluster_security_group(self):
        self.remove_augments()
        session_factory = self.replay_flight_data("test_rdscluster_sg_filter")
        p = self.load_policy(
            {
                "name": "rdscluster-sg",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DatabaseName"], "devtest")

    def test_rdscluster_subnet(self):
        self.remove_augments()
        session_factory = self.replay_flight_data("test_rdscluster_subnet")
        p = self.load_policy(
            {
                "name": "rdscluster-sub",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "subnet", "key": "MapPublicIpOnLaunch", "value": True}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DatabaseName"], "devtest")

    def test_rdscluster_simple(self):
        self.remove_augments()
        session_factory = self.replay_flight_data("test_rdscluster_simple")
        p = self.load_policy(
            {"name": "rdscluster-simple", "resource": "rds-cluster"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_rdscluster_simple_filter(self):
        self.remove_augments()
        session_factory = self.replay_flight_data("test_rdscluster_simple")
        p = self.load_policy(
            {
                "name": "rdscluster-simple-filter",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "value", "key": "DBClusterIdentifier", "value": "bbb"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_kms_alias(self):
        session_factory = self.replay_flight_data("test_rdscluster_kms_alias", region="us-east-2")
        p = self.load_policy(
            {
                "name": "rds-cluster-aws-kms-key-filter",
                "resource": "rds-cluster",
                "source": "config",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "^(alias/aws/)",
                        "op": "regex",
                    }
                ],
            },
            config={"region": "us-east-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_delete(self):
        self.remove_augments()
        session_factory = self.replay_flight_data("test_rdscluster_delete")
        p = self.load_policy(
            {
                "name": "rdscluster-delete",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "value", "key": "DBClusterIdentifier", "value": "bbb"}
                ],
                "actions": [{"type": "delete", "delete-instances": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_delete_with_instances(self):
        self.remove_augments()
        session_factory = self.replay_flight_data(
            "test_rdscluster_delete_with_instances"
        )
        p = self.load_policy(
            {
                "name": "rdscluster-delete",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "value", "key": "DBClusterIdentifier", "value": "bbb"}
                ],
                "actions": [{"type": "delete", "delete-instances": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_retention(self):
        self.remove_augments()
        session_factory = self.replay_flight_data("test_rdscluster_retention")
        p = self.load_policy(
            {
                "name": "rdscluster-delete",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "value", "key": "DBClusterIdentifier", "value": "bbb"}
                ],
                "actions": [{"type": "retention", "days": 21}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_snapshot(self):
        self.remove_augments()
        session_factory = self.replay_flight_data("test_rdscluster_snapshot")
        p = self.load_policy(
            {
                "name": "rdscluster-snapshot",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "value", "key": "DBClusterIdentifier", "value": "bbb"}
                ],
                "actions": [{"type": "snapshot"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_modify_rds_cluster(self):
        session_factory = self.replay_flight_data("test_modify_rds_cluster")
        p = self.load_policy(
            {
                "name": "modify-db-cluster",
                "resource": "rds-cluster",
                "filters": [{"DeletionProtection": True}],
                "actions": [{
                    "type": "modify-db-cluster",
                    "attributes": {
                        "DeletionProtection": False}
                }]
            },
            session_factory=session_factory, config={'account_id': '644160558196'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("rds")
        cluster = client.describe_db_clusters(
            DBClusterIdentifier='mytest')
        self.assertFalse(cluster['DBClusters'][0]['DeletionProtection'])

    def test_modify_rds_cluster_provisoned(self):
        session_factory = self.replay_flight_data("test_modify_rds_cluster_provisoned")
        p = self.load_policy(
            {
                "name": "modify-db-cluster",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "value", "key": "DBClusterIdentifier", "value": "database-1"}
                ],
                "actions": [{"type": "retention", "days": 7}],
            },
            session_factory=session_factory, config={'account_id': '644160558196'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get("DBClusterIdentifier", 0), "database-1")
        client = session_factory().client("rds")
        cluster = client.describe_db_clusters(
            DBClusterIdentifier="database-1")
        self.assertEqual(cluster['DBClusters'][0]['BackupRetentionPeriod'], 7)

    def test_modify_rds_cluster_serverless_v2(self):
        session_factory = self.replay_flight_data("test_modify_rds_cluster_serverless_v2")
        p = self.load_policy(
            {
                "name": "modify-db-cluster",
                "resource": "rds-cluster",
                "filters": [
                    {"type": "value", "key": "DBClusterIdentifier", "value": "database-2"}
                ],
                "actions": [{"type": "retention", "days": 8}],
            },
            session_factory=session_factory, config={'account_id': '644160558196'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get("DBClusterIdentifier", 0), "database-2")
        client = session_factory().client("rds")
        cluster = client.describe_db_clusters(
            DBClusterIdentifier="database-2")
        self.assertEqual(cluster['DBClusters'][0]['BackupRetentionPeriod'], 8)

    def test_rdscluster_tag_augment(self):
        session_factory = self.replay_flight_data("test_rdscluster_tag_augment")
        p = self.load_policy(
            {
                "name": "rdscluster-tag-augment",
                "resource": "rds-cluster",
                "filters": [{"tag:cfoo": "cbar"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_tag_and_remove(self):
        self.patch(RDSCluster, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_rdscluster_tag_and_remove")
        client = session_factory().client("rds")

        p = self.load_policy(
            {
                "name": "rds-cluster-tag",
                "resource": "rds-cluster",
                "filters": [{"DBClusterIdentifier": "c7ntest"}],
                "actions": [{"type": "tag", "key": "xyz", "value": "hello world"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        arn = p.resource_manager.generate_arn(resources[0]["DBClusterIdentifier"])

        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("xyz" in tag_map)

        policy = self.load_policy(
            {
                "name": "rds-cluster-remove-tag",
                "resource": "rds-cluster",
                "filters": [{"tag:xyz": "not-null"}],
                "actions": [{"type": "remove-tag", "tags": ["xyz"]}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertFalse("xyz" in tag_map)

    def test_rdscluster_mark_match_unmark(self):
        session_factory = self.replay_flight_data("test_rdscluster_mark_and_match")
        client = session_factory().client("rds")

        # mark
        p = self.load_policy(
            {
                "name": "rds-mark",
                "resource": "rds-cluster",
                "filters": [{"DBClusterIdentifier": "c7ntest"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_next",
                        "days": 1,
                        "op": "delete",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # assert marked
        arn = p.resource_manager.generate_arn(resources[0]["DBClusterIdentifier"])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("custodian_next" in tag_map)

        # match marked
        policy = self.load_policy(
            {
                "name": "rds-mark-filter",
                "resource": "rds-cluster",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_next",
                        "op": "delete",
                        "skew": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        # unmark
        policy = self.load_policy(
            {
                "name": "rds-mark-filter",
                "resource": "rds-cluster",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_next",
                        "op": "delete",
                        "skew": 1,
                    }
                ],
                "actions": [{"type": "unmark", "tags": ["custodian_next"]}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        # assert unmarked
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertFalse("custodian_next" in tag_map)

    def test_run_cluster_method(self):

        output = self.capture_logging('custodian.rds-cluster')

        def foobar(DBClusterIdentifier):
            raise ValueError("eek")

        # unspecified
        self.assertRaises(
            ValueError, _run_cluster_method, foobar, {'DBClusterIdentifier': 'mytest'})

        # ignored
        try:
            _run_cluster_method(foobar, {'DBClusterIdentifier': 'mytest'}, ValueError)
        except ValueError:
            self.fail("Shouldn't raise")
        finally:
            self.assertEqual(output.getvalue(), "")

        # warn
        try:
            _run_cluster_method(
                foobar, {'DBClusterIdentifier': 'mytest'}, warn=(ValueError, KeyError))
        except ValueError:
            self.fail("Shouldn't raise")
        finally:
            self.assertTrue("eek" in output.getvalue())

    def test_stop(self):
        factory = self.replay_flight_data("test_rdscluster_stop")
        p = self.load_policy(
            {"name": "rdscluster",
             "resource": "rds-cluster",
             "filters": [{'DBClusterIdentifier': 'mytest'}],
             'actions': ['stop']},
            session_factory=factory, config={'account_id': '644160558196'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Status'], 'available')

        client = factory().client('rds')
        cluster = client.describe_db_clusters(
            DBClusterIdentifier='mytest').get('DBClusters')[0]
        self.assertEqual(cluster['Status'], 'stopping')

    def test_start(self):
        factory = self.replay_flight_data("test_rdscluster_start")
        p = self.load_policy(
            {"name": "rdscluster",
             "resource": "rds-cluster",
             "filters": [{'DBClusterIdentifier': 'mytest'}],
             'actions': ['start']},
            session_factory=factory, config={'account_id': '644160558196'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Status'], 'stopped')

        client = factory().client('rds')
        cluster = client.describe_db_clusters(
            DBClusterIdentifier='mytest').get('DBClusters')[0]
        self.assertEqual(cluster['Status'], 'starting')

    def test_rdscluster_snapshot_count_filter(self):
        factory = self.replay_flight_data("test_rdscluster_snapshot_count_filter")
        p = self.load_policy(
            {
                "name": "rdscluster-snapshot-count-filter",
                "resource": "rds-cluster",
                "filters": [{"type": "consecutive-snapshots", "days": 2}],
            },
            session_factory=factory,
        )
        with mock_datetime_now(parser.parse("2022-03-30T00:00:00+00:00"), c7n.resources.rdscluster):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_consecutive_aws_backups_count_filter(self):
        session_factory = self.replay_flight_data(
            "test_rdscluster_consecutive_aws_backups_count_filter")
        p = self.load_policy(
            {
                "name": "rdscluster_consecutive_aws_backups_count_filter",
                "resource": "rds-cluster",
                "filters": [
                    {
                        "type": "consecutive-aws-backups",
                        "count": 2,
                        "period": "days",
                        "status": "COMPLETED"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-09-09T00:00:00+00:00"), c7n.filters.backup):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_pending_maintenance(self):
        session_factory = self.replay_flight_data("test_rdscluster_pending_maintenance")
        p = self.load_policy(
            {
                "name": "rds-cluster-pending-maintenance",
                "resource": "rds-cluster",
                "filters": [
                    {
                        "type": "pending-maintenance"
                    },
                    {
                        "type": "value",
                        "key": '"c7n:PendingMaintenance"[].PendingMaintenanceActionDetails['
                               '].Action',
                        "op": "intersect",
                        "value": ["db-upgrade"]
                    }
                ],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)


class RDSClusterSnapshotTest(BaseTest):

    def test_rdscluster_snapshot_config(self):
        session_factory = self.replay_flight_data("test_rdscluster_snapshot_config")
        p = self.load_policy(
            {"name": "rdscluster-snapshot-simple",
             "source": "config",
             "resource": "rds-cluster-snapshot"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        p2 = self.load_policy(
            {"name": "rdscluster-snapshot-descr",
             "resource": "rds-cluster-snapshot"},
            session_factory=session_factory)
        rm = p2.resource_manager
        resources2 = rm.get_resources([resources[-1][rm.resource_type.id]])
        self.maxDiff = None
        # placebo mangles the utc tz with its own class, also our account rewriter
        # mangles the timestamp string :-(
        for k in ('ClusterCreateTime', 'SnapshotCreateTime'):
            for r in (resources[-1], resources2[0]):
                r.pop(k)
        self.assertEqual(resources[-1], resources2[0])

    def test_rdscluster_snapshot_simple(self):
        session_factory = self.replay_flight_data("test_rdscluster_snapshot_simple")
        p = self.load_policy(
            {"name": "rdscluster-snapshot-simple", "resource": "rds-cluster-snapshot"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_rdscluster_snapshot_get_resources(self):
        session_factory = self.replay_flight_data('test_rds_cluster_snapshot_get_resources')
        p = self.load_policy(
            {
                'name': 'rdscluster-get',
                'resource': 'aws.rds-cluster-snapshot'
            },
            session_factory=session_factory)
        resources = p.resource_manager.get_resources([
            'test-cluster-final-snapshot',
            'invalid',
            'rds:database-1-2020-04-27-05-58'])
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            {'rds:database-1-2020-04-27-05-58', 'test-cluster-final-snapshot'},
            {r['DBClusterSnapshotIdentifier'] for r in resources})
        self.assertEqual(
            {len(r['Tags']) for r in resources},
            {1, 0})

    def test_rdscluster_snapshot_cross_account(self):
        session_factory = self.replay_flight_data(
            'test_rds_cluster_snapshot_cross_account_everyone_only'
        )
        p = self.load_policy(
            {
                'name': 'rdscluster-snapshot-xaccount',
                'resource': 'aws.rds-cluster-snapshot',
                'filters': [
                    {'type': 'cross-account'}]
            },
            session_factory=session_factory)
        resources = p.run()
        violations = {
            r["DBClusterSnapshotIdentifier"]: r["c7n:CrossAccountViolations"]
            for r in resources
        }
        self.assertEqual(len(violations), 2)
        self.assertEqual(violations["c7n-testing-public"], ["all"])
        self.assertEqual(violations["c7n-testing-shared"], ['111111111111'])

    def test_rdscluster_snapshot_cross_account_everyone_only(self):
        session_factory = self.replay_flight_data(
            'test_rds_cluster_snapshot_cross_account_everyone_only'
        )
        p = self.load_policy(
            {
                'name': 'rdscluster-snapshot-xaccount-everyone',
                'resource': 'aws.rds-cluster-snapshot',
                'filters': [
                    {'type': 'cross-account',
                     'everyone_only': True}]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DBClusterSnapshotIdentifier'], 'c7n-testing-public')
        self.assertEqual(resources[0]['c7n:CrossAccountViolations'], ['all'])

    def test_rdscluster_snapshot_simple_filter(self):
        session_factory = self.replay_flight_data("test_rdscluster_snapshot_simple")
        p = self.load_policy(
            {
                "name": "rdscluster-snapshot-simple-filter",
                "resource": "rds-cluster-snapshot",
                "filters": [
                    {"type": "value", "key": "StorageEncrypted", "value": False}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_snapshot_age_filter(self):
        factory = self.replay_flight_data("test_rdscluster_snapshot_simple")
        p = self.load_policy(
            {
                "name": "rdscluster-snapshot-age-filter",
                "resource": "rds-cluster-snapshot",
                "filters": [{"type": "age", "days": 7}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_rdscluster_snapshot_trim(self):
        factory = self.replay_flight_data("test_rdscluster_snapshot_delete")
        p = self.load_policy(
            {
                "name": "rdscluster-snapshot-trim",
                "resource": "rds-cluster-snapshot",
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def _get_effective_permissions(self, client, snapshot_id):
        attributes = client.describe_db_cluster_snapshot_attributes(
            DBClusterSnapshotIdentifier=snapshot_id
        )["DBClusterSnapshotAttributesResult"]["DBClusterSnapshotAttributes"]
        attr_map = {
            attr["AttributeName"]: attr["AttributeValues"]
            for attr in attributes
        }
        return set(attr_map.get("restore", []))

    def test_set_permissions(self):
        session_factory = self.replay_flight_data(
            "test_rdscluster_snapshot_set_permissions",
            region="us-east-2"
        )
        target_snapshot_id = "test"
        keep = "644160558196"
        remove = "123456789012"
        add = "234567890123"
        policy = self.load_policy(
            {
                "name": "rds-snapshot-remove-cross-account",
                "resource": "rds-cluster-snapshot",
                "source": "config",
                "query": [
                    {"clause": f"resourceId = '{target_snapshot_id}'"}],
                "actions": [
                    {"type": "set-permissions", "add": [add], "remove": [remove, "all"]}
                ]
            },
            session_factory=session_factory,
            config={"region": "us-east-2"},
        )
        client = session_factory().client("rds")
        restore_permissions_before = self._get_effective_permissions(
            client,
            target_snapshot_id,
        )
        self.assertTrue({keep, remove, "all"}.issubset(restore_permissions_before))

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        restore_permissions_after = self._get_effective_permissions(
            client,
            target_snapshot_id,
        )
        self.assertTrue({keep, add}.issubset(restore_permissions_after))
        self.assertEqual({remove, "all"}.intersection(restore_permissions_after), set())

    def test_remove_matched_permissions(self):
        session_factory = self.replay_flight_data(
            "test_rdscluster_snapshot_remove_matched_permissions",
            region="us-east-2"
        )
        target_snapshot_id = "test"
        keep = "644160558196"
        remove = "123456789012"
        policy = self.load_policy(
            {
                "name": "rds-snapshot-remove-cross-account",
                "resource": "rds-cluster-snapshot",
                "source": "config",
                "query": [
                    {"clause": f"resourceId = '{target_snapshot_id}'"}],
                "filters": [
                    {"type": "cross-account", "whitelist": [keep]},
                ],
                "actions": [
                    {"type": "set-permissions", "remove": "matched"}
                ]
            },
            session_factory=session_factory,
            config={"region": "us-east-2"},
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        restore_permissions_before = set(resources[0]["c7n:attributes"]["restore"])
        self.assertTrue({keep, remove}.issubset(restore_permissions_before))

        restore_permissions_after = self._get_effective_permissions(
            session_factory().client("rds"),
            resources[0]["DBClusterSnapshotIdentifier"]
        )
        self.assertIn(keep, restore_permissions_after)
        self.assertNotIn(remove, restore_permissions_after)

    def test_clear_permissions(self):
        session_factory = self.replay_flight_data(
            "test_rdscluster_snapshot_clear_permissions",
            region="us-east-2"
        )
        target_snapshot_id = "test"
        policy = self.load_policy(
            {
                "name": "rds-snapshot-remove-cross-account",
                "resource": "rds-cluster-snapshot",
                "source": "config",
                "query": [
                    {"clause": f"resourceId = '{target_snapshot_id}'"}],
                "actions": [
                    {"type": "set-permissions"}
                ]
            },
            session_factory=session_factory,
            config={"region": "us-east-2"},
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        restore_permissions_before = set(resources[0]["c7n:attributes"]["restore"])
        self.assertGreater(len(restore_permissions_before), 0)

        restore_permissions_after = self._get_effective_permissions(
            session_factory().client("rds"),
            resources[0]["DBClusterSnapshotIdentifier"]
        )
        self.assertEqual(len(restore_permissions_after), 0)

    def test_rds_cluster_cross_region_copy(self):
        # preconditions
        # rds cluster snapshot, encrypted in region with kms, and tags
        factory = self.replay_flight_data("test_rds_cluster_snapshot_region_copy")
        client = factory().client("rds", region_name="us-east-2")
        self.change_environment(AWS_DEFAULT_REGION="us-east-1")
        p = self.load_policy(
            {
                "name": "rds-cluster-snapshot-region-copy",
                "resource": "rds-cluster-snapshot",
                "filters": [{"DBClusterSnapshotIdentifier": "test-cluster-final-snapshot"}],
                "actions": [
                    {
                        "type": "region-copy",
                        "target_region": "us-east-2",
                        "tags": {"migrated_from": "us-east-1"},
                        "target_key": "b10f842a-feb7-4318-92d5-0640a75b7688",
                    }
                ],
            },
            config=dict(region="us-east-1"),
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        snapshots = client.describe_db_cluster_snapshots(
            DBClusterSnapshotIdentifier=resources[0]["c7n:CopiedClusterSnapshot"].rsplit(":", 1)[1]
        )[
            "DBClusterSnapshots"
        ]
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["DBClusterIdentifier"], "test-cluster")
        tags = {
            t["Key"]: t["Value"]
            for t in client.list_tags_for_resource(
                ResourceName=resources[0]["c7n:CopiedClusterSnapshot"]
            )[
                "TagList"
            ]
        }
        self.assertEqual(
            {
                "migrated_from": "us-east-1",
                "app": "mgmt-portal",
                "env": "staging",
                "workload-type": "other",
            },
            tags,
        )


class TestRDSClusterParameterGroupFilter(BaseTest):

    def test_param_value_cases(self):
        session_factory = self.replay_flight_data('test_rdsclusterparamgroup_filter')
        policy = self.load_policy(
            {
                "name": "rds-aurora-paramter-group-check",
                "resource": "rds-cluster",
                "filters": [
                    {
                        "type": "db-cluster-parameter",
                        "key": "tls_version",
                        "op": "ne",
                        "value": "TLSv1.2"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = policy.resource_manager.resources()
        self.assertEqual(len(resources), 2)


class TestRDSDBShardGroup(BaseTest):
    def test_rds_db_shard_group(self):
        session_factory = self.replay_flight_data('test_rds_db_shard_group')
        p = self.load_policy(
            {
                "name": "rds-db-shard-group",
                "resource": "rds-db-shard-group",
                "filters": [
                    {
                        "type": "value",
                        "key": "PubliclyAccessible",
                        "value": False
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DBShardGroupIdentifier'], 'db-shard-1')
