# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
from unittest.mock import MagicMock
import time
import datetime
import logging
from c7n.testing import mock_datetime_now
from dateutil import parser
import c7n.resources.redshift
import c7n.filters.backup


class TestRedshift(BaseTest):

    def test_redshift_pause(self):
        factory = self.replay_flight_data('test_redshift_pause')
        p = self.load_policy({
            'name': 'redshift-pause',
            'resource': 'redshift',
            'filters': [{'ClusterStatus': 'available'}],
            'actions': ['pause']},
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['ClusterIdentifier'] == 'redshift-cluster-1'
        if self.recording:
            time.sleep(2)
        client = factory().client('redshift')
        cluster = client.describe_clusters(
            ClusterIdentifier=resources[0]['ClusterIdentifier']).get('Clusters')[0]
        assert cluster['ClusterStatus'] == 'pausing'

    def test_redshift_resume(self):
        factory = self.replay_flight_data('test_redshift_resume')
        p = self.load_policy({
            'name': 'redshift-pause',
            'resource': 'redshift',
            'filters': [{'ClusterStatus': 'paused'}],
            'actions': ['resume']},
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['ClusterIdentifier'] == 'redshift-cluster-1'
        if self.recording:
            time.sleep(2)
        client = factory().client('redshift')
        cluster = client.describe_clusters(
            ClusterIdentifier=resources[0]['ClusterIdentifier']).get('Clusters')[0]
        assert cluster['ClusterStatus'] == 'resuming'

    def test_redshift_security_group_filter(self):
        factory = self.replay_flight_data("test_redshift_security_group_filter")
        p = self.load_policy(
            {
                "name": "redshift-query",
                "resource": "redshift",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ClusterIdentifier"], "dev-test")

    def test_redshift_subnet_filter(self):
        factory = self.replay_flight_data("test_redshift_subnet_filter")
        p = self.load_policy(
            {
                "name": "redshift-query",
                "resource": "redshift",
                "filters": [
                    {"type": "subnet", "key": "MapPublicIpOnLaunch", "value": True}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ClusterIdentifier"], "dev-test")

    def test_redshift_query(self):
        factory = self.replay_flight_data("test_redshift_query")
        p = self.load_policy(
            {"name": "redshift-query", "resource": "redshift"}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(resources, [])

    def test_redshift_parameter(self):
        factory = self.replay_flight_data("test_redshift_parameter")
        p = self.load_policy(
            {
                "name": "redshift-ssl",
                "resource": "redshift",
                "filters": [{"type": "param", "key": "require_ssl", "value": False}],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_simple_tag_filter(self):
        factory = self.replay_flight_data("test_redshift_tag_filter")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-tag-filter",
                "resource": "redshift",
                "filters": [{"tag:maid_status": "not-null"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(resources[0]["ClusterIdentifier"])
        tags = client.describe_tags(ResourceName=arn)["TaggedResources"]
        tag_map = {t["Tag"]["Key"] for t in tags}
        self.assertTrue("maid_status" in tag_map)

    def test_redshift_cluster_mark(self):
        factory = self.replay_flight_data("test_redshift_cluster_mark")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-cluster-mark",
                "resource": "redshift",
                "filters": [
                    {"type": "value", "key": "ClusterIdentifier", "value": "c7n"}
                ],
                "actions": [{"type": "mark-for-op", "days": 30, "op": "delete"}],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(resources[0]["ClusterIdentifier"])
        tags = client.describe_tags(ResourceName=arn)["TaggedResources"]
        tag_map = {t["Tag"]["Key"] for t in tags}
        self.assertTrue("maid_status" in tag_map)

    def test_redshift_cluster_unmark(self):
        factory = self.replay_flight_data("test_redshift_cluster_unmark")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-cluster-unmark",
                "resource": "redshift",
                "filters": [
                    {"type": "value", "key": "ClusterIdentifier", "value": "c7n"}
                ],
                "actions": [{"type": "unmark"}],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(resources[0]["ClusterIdentifier"])
        tags = client.describe_tags(ResourceName=arn)["TaggedResources"]
        tag_map = {t["Tag"]["Key"] for t in tags}
        self.assertFalse("maid_status" in tag_map)

    def test_redshift_delete(self):
        factory = self.replay_flight_data("test_redshift_delete")
        p = self.load_policy(
            {
                "name": "redshift-ssl",
                "resource": "redshift",
                "filters": [{"ClusterIdentifier": "c7n-test"}],
                "actions": [{"type": "delete", "skip-snapshot": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_default_vpc(self):
        session_factory = self.replay_flight_data("test_redshift_default_vpc")
        p = self.load_policy(
            {
                "name": "redshift-default-filters",
                "resource": "redshift",
                "filters": [{"type": "default-vpc"}],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_retention(self):
        session_factory = self.replay_flight_data("test_redshift_retention")
        p = self.load_policy(
            {
                "name": "redshift-retention",
                "resource": "redshift",
                "filters": [
                    {"type": "value", "key": "ClusterIdentifier", "value": "aaa"}
                ],
                "actions": [{"type": "retention", "days": 21}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_snapshot(self):
        factory = self.replay_flight_data("test_redshift_snapshot")
        client = factory().client("redshift")
        cluster_tags = []
        p = self.load_policy(
            {
                "name": "redshift-snapshot",
                "resource": "redshift",
                "filters": [
                    {
                        "type": "value",
                        "key": "ClusterIdentifier",
                        "value": "test-cluster",
                        "op": "eq",
                    }
                ],
                "actions": [{"type": "snapshot"}],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        cluster = client.describe_clusters(
            ClusterIdentifier=resources[0]["ClusterIdentifier"]
        )
        id_cluster = cluster.get("Clusters")[0].get("ClusterIdentifier")
        snapshot = client.describe_cluster_snapshots(
            SnapshotIdentifier="backup-test-cluster-2017-01-12"
        )
        get_snapshots = snapshot.get("Snapshots")
        id_snapshot = get_snapshots[0].get("ClusterIdentifier")
        tag_snapshot = get_snapshots[0].get("Tags")
        self.assertEqual(id_cluster, id_snapshot)
        arn = p.resource_manager.generate_arn(resources[0]["ClusterIdentifier"])
        cluster_tags_array = client.describe_tags(ResourceName=arn)["TaggedResources"]
        for cluster_tag_elem in cluster_tags_array:
            cluster_tags.append(cluster_tag_elem["Tag"])
        self.assertEqual(cluster_tags, tag_snapshot)

    def test_redshift_vpc_routing(self):
        factory = self.replay_flight_data("test_redshift_vpc_routing")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-vpc-routing",
                "resource": "redshift",
                "filters": [
                    {"type": "value", "key": "EnhancedVpcRouting", "value": True}
                ],
                "actions": [{"type": "enable-vpc-routing", "value": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Ensure that the cluster starts to modify EnhancedVpcRouting value.
        response = client.describe_clusters(
            ClusterIdentifier=resources[0]["ClusterIdentifier"]
        )
        cluster = response["Clusters"][0]
        self.assertEqual(
            cluster["ClusterIdentifier"], resources[0]["ClusterIdentifier"]
        )
        self.assertEqual(cluster["ClusterStatus"], "modifying")
        self.assertTrue(cluster["PendingModifiedValues"]["EnhancedVpcRouting"])

    def test_redshift_public_access(self):
        session_factory = self.replay_flight_data("test_redshift_public_access")
        client = session_factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-set-public-access",
                "resource": "redshift",
                "filters": [{"PubliclyAccessible": True}],
                "actions": [{"type": "set-public-access", "state": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        cluster = client.describe_clusters(ClusterIdentifier="c7n-rs")["Clusters"][0]
        self.assertEqual(
            cluster["ClusterIdentifier"], resources[0]["ClusterIdentifier"]
        )
        self.assertFalse(cluster["PubliclyAccessible"])

    def test_redshift_kms_alias(self):
        factory = self.replay_flight_data("test_redshift_kms_key_filter")
        p = self.load_policy(
            {
                "name": "redshift-kms-alias",
                "resource": "redshift",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "^(alias/aws/)",
                        "op": "regex"
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['KmsKeyId'],
            'arn:aws:kms:us-east-1:644160558196:key/8785aeb9-a616-4e2b-bbd3-df3cde76bcc5') # NOQA

    def test_redshift_set_attributes(self):
        factory = self.replay_flight_data("test_redshift_set_attributes")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-allow-version-upgrade",
                "resource": "redshift",
                "filters": [
                    {
                        "type": "value",
                        "key": "AllowVersionUpgrade",
                        "value": False,
                    }
                ],
                "actions": [{
                    "type": "set-attributes",
                    "attributes": {
                        "AllowVersionUpgrade": True,
                        "MaintenanceTrackName": "current"
                    }
                }]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        cluster = client.describe_clusters(ClusterIdentifier="test")["Clusters"][0]
        self.assertEqual(
            cluster["ClusterIdentifier"], resources[0]["ClusterIdentifier"]
        )
        self.assertTrue(cluster['AllowVersionUpgrade'])
        self.assertEqual(cluster["MaintenanceTrackName"], "current")

    def test_redshift_set_attributes_no_change(self):
        factory = self.replay_flight_data("test_redshift_set_attributes")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-allow-version-upgrade",
                "resource": "redshift",
                "actions": [{
                    "type": "set-attributes",
                    "attributes": {
                        "PubliclyAccessible": False,
                    }
                }]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        cluster = client.describe_clusters(ClusterIdentifier="test")["Clusters"][0]
        self.assertEqual(
            cluster["ClusterIdentifier"], resources[0]["ClusterIdentifier"]
        )
        self.assertFalse(cluster['PubliclyAccessible'])

    def test_redshift_set_attributes_error(self):
        factory = self.replay_flight_data("test_redshift_set_attributes")

        client = factory().client("redshift")
        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'
        mock_factory().client(
            'redshift').exceptions.ClusterNotFoundFault = (
                client.exceptions.ClusterNotFoundFault)

        mock_factory().client('redshift').modify_cluster.side_effect = (
            client.exceptions.ClusterNotFoundFault(
                {'Error': {'Code': 'xyz'}},
                operation_name='modify_cluster'))
        p = self.load_policy(
            {
                "name": "redshift-allow-version-upgrade",
                "resource": "redshift",
                "actions": [{
                    "type": "set-attributes",
                    "attributes": {
                        "AllowVersionUpgrade": True,
                    }
                }]
            },
            session_factory=mock_factory,
        )

        try:
            p.resource_manager.actions[0].process(
                [{'Id': 'abc'}])
        except client.exceptions.ClusterNotFoundFault:
            self.fail('should not raise')
        mock_factory().client('redshift').modify_cluster.assert_called_once()

    def test_redshift_consecutive_snapshot_count_filter(self):
        session_factory = self.replay_flight_data("test_redshift_consecutive_snapshot_count_filter")
        p = self.load_policy(
            {
                "name": "redshift_consecutive_snapshot_count_filter",
                "resource": "redshift",
                "filters": [
                    {
                        "type": "consecutive-snapshots",
                        "count": 2,
                        "period": "days",
                        "status": "available"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-09-09T00:00:00+00:00"), c7n.resources.redshift):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:RedshiftSnapshots'][0]['Status'], "available")
        self.assertEqual(resources[0]['c7n:RedshiftSnapshots'][0]['SnapshotCreateTime'],
            datetime.datetime(2022, 9, 9, 22, 4, 52, 776000, tzinfo=datetime.timezone.utc))

    def test_redshift_consecutive_snapshot_hourly_count_filter(self):
        session_factory = self.replay_flight_data(
            "test_redshift_consecutive_snapshot_count_filter")
        p = self.load_policy(
            {
                "name": "redshift_consecutive_snapshot_hourly_count_filter",
                "resource": "redshift",
                "filters": [
                    {
                        "type": "consecutive-snapshots",
                        "count": 2,
                        "period": "hours",
                        "status": "available"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-09-08T21:00:00+00:00"), c7n.resources.redshift):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_consecutive_snapshot_weekly_count_filter(self):
        session_factory = self.replay_flight_data(
            "test_redshift_consecutive_snapshot_count_filter")
        p = self.load_policy(
            {
                "name": "redshift_consecutive_snapshot_weekly_count_filter",
                "resource": "redshift",
                "filters": [
                    {
                        "type": "consecutive-snapshots",
                        "count": 1,
                        "period": "weeks",
                        "status": "available"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-09-09T00:00:00+00:00"), c7n.resources.redshift):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_consecutive_aws_backups_count_filter(self):
        session_factory = self.replay_flight_data(
            "test_redshift_consecutive_aws_backups_count_filter")
        p = self.load_policy(
            {
                "name": "redshift_consecutive_aws_backups_count_filter",
                "resource": "redshift",
                "filters": [
                    {
                        "type": "consecutive-aws-backups",
                        "count": 1,
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


class TestRedshiftSnapshot(BaseTest):

    def test_redshift_snapshot_simple(self):
        session_factory = self.replay_flight_data("test_redshift_snapshot_simple")
        p = self.load_policy(
            {"name": "redshift-snapshot-simple", "resource": "redshift-snapshot"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_redshift_snapshot_simple_filter(self):
        session_factory = self.replay_flight_data("test_redshift_snapshot_simple")
        p = self.load_policy(
            {
                "name": "redshift-snapshot-simple-filter",
                "resource": "redshift-snapshot",
                "filters": [{"type": "value", "key": "Encrypted", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_snapshot_age_filter(self):
        factory = self.replay_flight_data("test_redshift_snapshot_simple")
        p = self.load_policy(
            {
                "name": "redshift-snapshot-age-filter",
                "resource": "redshift-snapshot",
                "filters": [{"type": "age", "days": 7}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_redshift_snapshot_delete(self):
        factory = self.replay_flight_data("test_redshift_snapshot_delete")
        p = self.load_policy(
            {
                "name": "redshift-snapshot-delete",
                "resource": "redshift-snapshot",
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_redshift_snapshot_mark(self):
        factory = self.replay_flight_data("test_redshift_snapshot_mark")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-snapshot-mark",
                "resource": "redshift-snapshot",
                "filters": [
                    {
                        "type": "value",
                        "key": "SnapshotIdentifier",
                        "value": "c7n-test-snapshot",
                    }
                ],
                "actions": [{"type": "mark-for-op", "days": 30, "op": "delete"}],
            },
            session_factory=factory, config={'account_id': '644160558196'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.get_arns(resources)
        tags = client.describe_tags(ResourceName=arn[0])["TaggedResources"]
        tag_map = {t["Tag"]["Key"] for t in tags}
        self.assertTrue("maid_status" in tag_map)

    def test_redshift_snapshot_unmark(self):
        factory = self.replay_flight_data("test_redshift_snapshot_unmark")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "redshift-snapshot-unmark",
                "resource": "redshift-snapshot",
                "filters": [
                    {
                        "type": "value",
                        "key": "SnapshotIdentifier",
                        "value": "c7n-test-snapshot",
                    }
                ],
                "actions": [{"type": "unmark"}],
            },
            session_factory=factory, config={'account_id': '644160558196'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.get_arns(resources)
        tags = client.describe_tags(ResourceName=arn[0])["TaggedResources"]
        tag_map = {t["Tag"]["Key"] for t in tags}
        self.assertFalse("maid_status" in tag_map)

    def test_redshift_snapshot_revoke_access(self):
        session_factory = self.replay_flight_data(
            "test_redshift_snapshot_revoke_cross_account"
        )
        p = self.load_policy(
            {
                "name": "redshift-snapshot-revoke-cross-account",
                "resource": "redshift-snapshot",
                "filters": [{"type": "cross-account", "whitelist": ["644160558196"]}],
                "actions": [{"type": "revoke-access"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["SnapshotIdentifier"], "c7n-rs-ss-last")
        self.assertEqual(resources[0]["c7n:CrossAccountViolations"], ["185106417252"])
        client = session_factory().client("redshift")
        ss = client.describe_cluster_snapshots(
            SnapshotIdentifier=resources[0]["SnapshotIdentifier"]
        )[
            "Snapshots"
        ]
        self.assertFalse(ss[0].get("AccountsWithRestoreAccess"))

    def test_redshift_snapshot_copy_related_tags(self):
        factory = self.replay_flight_data("test_redshift_snapshot_copy_related_tags")
        client = factory().client("redshift")
        p = self.load_policy(
            {
                "name": "rds-snapshot-copy-related-tags",
                "resource": "redshift-snapshot",
                "filters": [{"tag:Owner": "absent"}],
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "key": "ClusterIdentifier",
                        "resource": "redshift",
                        "tags": ["Owner"]
                    }],
            },
            session_factory=factory,
        )
        output = self.capture_logging("custodian.actions", level=logging.INFO)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        log_output = output.getvalue()
        self.assertIn("Tagged 2 resources from related", log_output)
        arns = p.resource_manager.get_arns(resources)
        for arn in arns:
            tags = client.describe_tags(ResourceName=arn)["TaggedResources"]
            tag_map = {t["Tag"]["Key"] for t in tags}
            self.assertTrue("Owner" in tag_map)


class TestModifyVpcSecurityGroupsAction(BaseTest):

    def test_redshift_remove_matched_security_groups(self):
        # Test conditions:
        # - running 2 Redshift clusters in default VPC
        #    - a default security group with id 'sg-7a3fcb13' exists
        #    - security group named PROD-ONLY-Test-Security-Group exists in
        #      VPC and is attached to one of the clusters
        #        - translates to 1 cluster marked non-compliant
        #
        # Results in 2 clusters with default Security Group attached
        session_factory = self.replay_flight_data(
            "test_redshift_remove_matched_security_groups"
        )
        p = self.load_policy(
            {
                "name": "redshift-remove-matched-security-groups",
                "resource": "redshift",
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
                "name": "redshift-verify-remove-matched-security-groups",
                "resource": "redshift",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        clean_resources = clean_p.run()

        # clusters autoscale across AZs, so they get -001, -002, etc appended
        self.assertIn("test-sg-fail", resources[0]["ClusterIdentifier"])

        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]["VpcSecurityGroups"]), 1)
        # show that it was indeed a replacement of security groups
        self.assertEqual(len(clean_resources[0]["VpcSecurityGroups"]), 1)
        self.assertEqual(len(clean_resources), 2)

    def test_redshift_add_security_group(self):
        # Test conditions:
        #    - running 2 redshift clusters in default VPC
        #    - a default security group with id 'sg-7a3fcb13' exists
        #      attached to both clusters
        #    - security group named PROD-ONLY-Test-Security-Group exists in
        #      VPC and is attached to 1/2 clusters
        #        - translates to 1 cluster marked to get new group attached
        #
        # Results in 1 cluster with default Security Group and
        # PROD-ONLY-Test-Security-Group

        session_factory = self.replay_flight_data("test_redshift_add_security_group")

        p = self.load_policy(
            {
                "name": "add-sg-to-prod-redshift",
                "resource": "redshift",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"},
                    {
                        "type": "value",
                        "key": "ClusterIdentifier",
                        "value": "test-sg-fail.*",
                        "op": "regex",
                    },
                ],
                "actions": [{"type": "modify-security-groups", "add": "sg-6360920a"}],
            },
            session_factory=session_factory,
        )
        clean_p = self.load_policy(
            {
                "name": "validate-add-sg-to-prod-redshift",
                "resource": "redshift",
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
        clean_resources = clean_p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn("test-sg-fail", resources[0]["ClusterIdentifier"])
        self.assertEqual(len(resources[0]["VpcSecurityGroups"]), 1)
        self.assertEqual(len(clean_resources[0]["VpcSecurityGroups"]), 2)
        self.assertEqual(len(clean_resources), 2)


class TestRedshiftLogging(BaseTest):

    annotation_key = 'c7n:logging'

    def test_enable_s3_logging(self):
        session_factory = self.replay_flight_data("test_redshift_enable_s3_logging")
        policy = self.load_policy(
            {
                "name": "test-enable-s3-logging",
                "resource": "redshift",
                "filters": [
                    {"type": "logging", "key": "LoggingEnabled", "value": False},
                    {"ClusterIdentifier": "test-logging-disabled"}
                ],
                "actions": [
                    {
                        "type": "set-logging",
                        "bucket": "redshiftlogtest2",
                        "prefix": "redshiftlogs",
                        "state": "enabled",
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterIdentifier'], 'test-logging-disabled')

        client = session_factory().client("redshift")

        redshift_id = resources[0]['ClusterIdentifier']
        result = client.describe_logging_status(
            ClusterIdentifier=redshift_id)
        result.pop('ResponseMetadata')

        self.assertTrue(result["LoggingEnabled"])
        self.assertEqual(
            result["BucketName"], "redshiftlogtest2"
        )
        self.assertEqual(
            result["S3KeyPrefix"], "redshiftlogs/"
        )

    def test_disable_s3_logging(self):
        session_factory = self.replay_flight_data("test_redshift_disable_s3_logging")
        policy = self.load_policy(
            {
                "name": "test-disable-s3-logging",
                "resource": "redshift",
                "filters": [
                    {"type": "logging", "key": "LoggingEnabled", "value": True},
                    {"ClusterIdentifier": "test-logging-enabled"}
                ],
                "actions": [
                    {
                        "type": "set-logging",
                        "state": "disabled",
                    }
                ],
            },
            session_factory=session_factory,
        )

        self.assertIn('redshift:DisableLogging', policy.get_permissions())
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterIdentifier'], 'test-logging-enabled')

        client = session_factory().client("redshift")

        redshift_id = resources[0]['ClusterIdentifier']
        result = client.describe_logging_status(
            ClusterIdentifier=redshift_id)
        result.pop('ResponseMetadata')

        self.assertFalse(result["LoggingEnabled"])


class TestReservedNode(BaseTest):
    def test_redshift_reserved_node_query(self):
        session_factory = self.replay_flight_data("test_redshift_reserved_node_query")
        p = self.load_policy(
            {
                "name": "redshift-reserved",
                "resource": "aws.redshift-reserved"
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ReservedNodeId"], "1ba8e2e3-bc01-4d65-b35d-a4a3e931547e")
