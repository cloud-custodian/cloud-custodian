# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
import json
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from unittest import mock

import boto3
from botocore.exceptions import ClientError
from c7n import tags
from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.resources import rds
from c7n.testing import mock_datetime_now
from dateutil import parser
from dateutil import tz as tzutil
import c7n.filters.backup

from .common import BaseTest, event_data
from pytest_terraform import terraform

logger = logging.getLogger(name="c7n.tests")


class RDSTest(BaseTest):

    def test_rds_config_event(self):
        event = event_data("rds-from-rule.json", "config")
        p = self.load_policy({"name": "rds", "resource": "rds"})
        source = p.resource_manager.get_source("config")
        resource_config = json.loads(event["invokingEvent"])["configurationItem"]
        resource = source.load_resource(resource_config)
        self.assertEqual(
            resource["Tags"], [{u"Key": u"workload-type", u"Value": u"other"}]
        )

    def test_rds_stop(self):
        session_factory = self.replay_flight_data("test_rds_stop")
        db_instance_id = "rds-test-instance-1"
        client = session_factory().client("rds")
        p = self.load_policy(
            {
                "name": "rds-stop",
                "resource": "rds",
                "filters": [{"DBInstanceIdentifier": db_instance_id}],
                "actions": ["stop"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBInstanceStatus"], "available")
        result = client.describe_db_instances(DBInstanceIdentifier=db_instance_id)
        self.assertEqual(result["DBInstances"][0]["DBInstanceStatus"], "stopping")

    def test_rds_start(self):
        session_factory = self.replay_flight_data("test_rds_start")
        db_instance_id = "rds-test-instance-2"
        client = session_factory().client("rds")
        p = self.load_policy(
            {
                "name": "rds-start",
                "resource": "rds",
                "filters": [{"DBInstanceIdentifier": db_instance_id}],
                "actions": ["start"],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBInstanceStatus"], "stopped")
        result = client.describe_db_instances(DBInstanceIdentifier=db_instance_id)
        self.assertEqual(result["DBInstances"][0]["DBInstanceStatus"], "starting")

    def test_rds_autopatch(self):
        session_factory = self.replay_flight_data("test_rds_auto_patch")
        p = self.load_policy(
            {
                "name": "rds-tags",
                "resource": "rds",
                "filters": [{"AutoMinorVersionUpgrade": False}],
                "actions": ["auto-patch"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_autopatch_with_window(self):
        window = "mon:23:00-tue:01:00"

        session_factory = self.replay_flight_data("test_rds_auto_patch_with_window")
        p = self.load_policy(
            {
                "name": "rds-tags",
                "resource": "rds",
                "filters": [{"AutoMinorVersionUpgrade": False}],
                "actions": [{"type": "auto-patch", "minor": True, "window": window}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        rds = session_factory().client("rds")
        details = rds.describe_db_instances(
            DBInstanceIdentifier=resources[0]["DBInstanceIdentifier"]
        )
        details = details["DBInstances"][0]

        self.assertTrue(details["AutoMinorVersionUpgrade"])
        self.assertEqual(details["PreferredMaintenanceWindow"], window)

    def test_rds_tags(self):
        session_factory = self.replay_flight_data("test_rds_tags")
        p = self.load_policy(
            {
                "name": "rds-tags",
                "resource": "rds",
                "filters": [{"tag:Platform": "postgres"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_tag_trim(self):
        self.patch(tags.TagTrim, "max_tag_count", 1)
        session_factory = self.replay_flight_data("test_rds_tag_trim")
        p = self.load_policy(
            {
                "name": "rds-tags",
                "resource": "rds",
                "filters": [{"tag:Platform": "postgres"}],
                "actions": [{"type": "tag-trim", "preserve": ["Name", "Owner"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_tag_and_remove(self):
        self.patch(rds.RDS, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_rds_tag_and_remove")
        client = session_factory().client("rds")

        p = self.load_policy(
            {
                "name": "rds-tag",
                "resource": "rds",
                "filters": [{"tag:Platform": "postgres"}],
                "actions": [{"type": "tag", "key": "xyz", "value": "hello world"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        arn = p.resource_manager.generate_arn(resources[0]["DBInstanceIdentifier"])

        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("xyz" in tag_map)

        policy = self.load_policy(
            {
                "name": "rds-remove-tag",
                "resource": "rds",
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

    def test_rds_mark_and_match(self):
        session_factory = self.replay_flight_data("test_rds_mark_and_match")
        p = self.load_policy(
            {
                "name": "rds-mark",
                "resource": "rds",
                "filters": [{"tag:Platform": "postgres"}],
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

        policy = self.load_policy(
            {
                "name": "rds-mark-filter",
                "resource": "rds",
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

    def test_rds_mark_hours(self):
        localtz = tzutil.gettz("Etc/UTC")
        dt = datetime.datetime.now(localtz)
        dt = dt.replace(
            year=2018, month=5, day=9, hour=21, minute=20, second=0, microsecond=0
        )
        session_factory = self.replay_flight_data("test_rds_mark_hours")
        session = session_factory(region="us-east-1")
        rds = session.client("rds")

        policy = self.load_policy(
            {
                "name": "rds-mark-5-hours",
                "resource": "rds",
                "filters": [{"tag:CreatorName": "absent"}],
                "actions": [{"type": "mark-for-op", "hours": 5, "op": "delete"}],
            },
            config={"account_id": "123456789012"},
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        resource = rds.list_tags_for_resource(
            ResourceName=resources[0]["DBInstanceArn"]
        )
        tags = [t["Value"] for t in resource["TagList"] if t["Key"] == "maid_status"]
        result = datetime.datetime.strptime(
            tags[0].strip().split("@", 1)[-1], "%Y/%m/%d %H%M %Z"
        ).replace(
            tzinfo=localtz
        )
        self.assertEqual(result, dt)

    def test_rds_marked_hours(self):
        session_factory = self.replay_flight_data("test_rds_marked_hours")
        policy = self.load_policy(
            {
                "name": "rds-marked-for-op-hours",
                "resource": "rds",
                "filters": [{"type": "marked-for-op", "op": "delete"}],
            },
            config={"account_id": "123456789012"},
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBInstanceIdentifier"], "db1")

    def test_rds_default_vpc(self):
        session_factory = self.replay_flight_data("test_rds_default_vpc")
        p = self.load_policy(
            {
                "name": "rds-default-filters",
                "resource": "rds",
                "filters": [{"type": "default-vpc"}],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_rds_kms_alias(self):
        session_factory = self.replay_flight_data("test_rds_kms_alias")
        p = self.load_policy(
            {
                "name": "rds-aws-managed-kms-keys-filters",
                "resource": "rds",
                "filters": [
                    {
                        "type": "kms-alias",
                        "key": "AliasName",
                        "value": "^(alias/aws/)",
                        "op": "regex",
                    }
                ],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_snapshot(self):
        session_factory = self.replay_flight_data("test_rds_snapshot")
        dt = datetime.datetime.now().replace(
            year=2017, month=12, day=11, hour=14, minute=9
        )
        suffix = dt.strftime("%Y-%m-%d-%H-%M")
        p = self.load_policy(
            {
                "name": "rds-snapshot",
                "resource": "rds",
                "filters": [{"DBInstanceIdentifier": "c7n-snapshot-test"}],
                "actions": [{"type": "snapshot"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory(region="us-east-1").client("rds")
        snapshot = client.describe_db_snapshots(
            DBInstanceIdentifier=resources[0]["DBInstanceIdentifier"]
        )[
            "DBSnapshots"
        ][
            0
        ]
        self.assertEqual(
            snapshot["DBSnapshotIdentifier"],
            "backup-%s-%s" % (resources[0]["DBInstanceIdentifier"], suffix),
        )

    def test_rds_retention(self):
        session_factory = self.replay_flight_data("test_rds_retention")
        p = self.load_policy(
            {
                "name": "rds-snapshot",
                "resource": "rds",
                "actions": [{"type": "retention", "days": 21}],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 5)

    def test_rds_retention_copy_tags(self):
        session_factory = self.replay_flight_data("test_rds_retention")
        p = self.load_policy(
            {
                "name": "rds-snapshot",
                "resource": "rds",
                "actions": [{"type": "retention", "days": 21, "copy-tags": True}],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 5)

    def test_rds_restore(self):
        self.patch(rds.RestoreInstance, "executor_factory", MainThreadExecutor)
        self.change_environment(AWS_DEFAULT_REGION="us-east-2")
        session_factory = self.replay_flight_data("test_rds_restore")
        client = session_factory().client("rds")
        instance_id = "mxtest"
        self.assertRaises(
            ClientError, client.describe_db_instances, DBInstanceIdentifier=instance_id
        )

        p = self.load_policy(
            {
                "name": "rds-restore",
                "resource": "rds-snapshot",
                "filters": [{"MasterUsername": "mxtester"}, "latest"],
                "actions": [
                    {
                        "type": "restore",
                        "restore_options": {"DBInstanceIdentifier": instance_id},
                    }
                ],
            },
            config=dict(region="us-east-2"),
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        try:
            client.describe_db_instances(DBInstanceIdentifier=instance_id)
        except ClientError:
            self.fail("DB Not found")

    def test_rds_delete_copy(self):
        session_factory = self.replay_flight_data("test_rds_delete_copy_restore")
        client = session_factory().client("rds")
        instance_id = "mxtest"
        db_info = client.describe_db_instances(DBInstanceIdentifier=instance_id)
        self.assertFalse(db_info["DBInstances"][0]["CopyTagsToSnapshot"])
        p = self.load_policy(
            {
                "name": "rds-delete",
                "resource": "rds",
                "filters": [{"DBInstanceIdentifier": instance_id}],
                "actions": [{"type": "delete", "copy-restore-info": True}],
            },
            config=dict(region="us-east-2"),
            session_factory=session_factory,
        )
        p.run()
        db_info = client.describe_db_instances(DBInstanceIdentifier=instance_id)
        self.assertTrue(db_info["DBInstances"][0]["CopyTagsToSnapshot"])
        snaps = p.resource_manager.get_resource_manager("rds-snapshot").get_resources(
            ("final-mxtest-2017-05-25",)
        )
        snap_keys = {t["Key"] for t in snaps[0]["Tags"]}
        self.assertTrue(snap_keys.issuperset(rds.RestoreInstance.restore_keys))

    def test_rds_delete(self):
        session_factory = self.replay_flight_data("test_rds_delete")
        p = self.load_policy(
            {
                "name": "rds-delete",
                "resource": "rds",
                "filters": [{"tag:Owner": "test"}],
                "actions": [{"type": "delete", "skip-snapshot": True}],
            },
            config=dict(region="us-west-2"),
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_available_engine_upgrades(self):
        session_factory = self.replay_flight_data(
            "test_rds_available_engine_upgrades", zdata=True
        )
        client = session_factory().client("rds")
        upgrades = rds._get_available_engine_upgrades(client)
        self.assertEqual(upgrades["postgres"]["9.3.1"], "9.3.14")
        self.assertEqual(
            upgrades["sqlserver-ex"]["10.50.6000.34.v1"], "10.50.6529.0.v1"
        )
        upgrades = rds._get_available_engine_upgrades(client, major=True)
        self.assertEqual(upgrades["postgres"]["9.3.1"], "9.4.9")
        self.assertEqual(upgrades["postgres"]["9.4.9"], "9.5.4")
        self.assertEqual(upgrades["sqlserver-ex"]["10.50.2789.0.v1"], "12.00.5000.0.v1")

    def test_rds_upgrade_available(self):
        session_factory = self.replay_flight_data("test_rds_minor_upgrade_available")
        p = self.load_policy(
            {
                "name": "rds-upgrade-available",
                "resource": "rds",
                "filters": [{"type": "upgrade-available", "major": True}],
                "actions": []
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r["EngineVersion"]: r.get("c7n-rds-engine-upgrade") for r in resources},
            {u"5.6.27": u"5.7.11"},
        )

    def test_rds_minor_upgrade_unavailable(self):
        session_factory = self.replay_flight_data("test_rds_minor_upgrade_unavailable")
        p = self.load_policy(
            {
                "name": "rds-upgrade-done",
                "resource": "rds",
                "filters": [{"type": "upgrade-available", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            {r["EngineVersion"]: r.get("c7n-rds-engine-upgrade") for r in resources},
            {u"5.5.41": u"5.5.46", u"5.6.29": None, u"5.7.11": None},
        )

    def test_rds_minor_upgrade_do(self):
        session_factory = self.replay_flight_data("test_rds_minor_upgrade_do")
        p = self.load_policy(
            {
                "name": "rds-upgrade-do",
                "resource": "rds",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_upgrade",
                        "op": "upgrade",
                        "skew": 4,
                    }
                ],
                "actions": [{"type": "upgrade", "immediate": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r["EngineVersion"]: r.get("c7n-rds-engine-upgrade") for r in resources},
            {u"5.6.29": u"5.6.35"},
        )
        self.assertEqual(resources[0]["DBInstanceIdentifier"], "c7n-mysql-test-03")
        self.assertEqual(resources[0]["EngineVersion"], "5.6.29")
        self.assertEqual(resources[0]["c7n-rds-engine-upgrade"], "5.6.35")

    def test_rds_eligible_start_stop(self):
        resource = {"DBInstanceIdentifier": "ABC",
                    "DBInstanceStatus": "available",
                    "Engine": "mysql"}
        self.assertTrue(rds._eligible_start_stop(resource, "available"))

        resource = {"DBInstanceIdentifier": "ABC",
                    "DBInstanceStatus": "stopped",
                    "Engine": "mysql"}
        self.assertFalse(rds._eligible_start_stop(resource, "available"))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "Engine": "postgres",
            "MultiAZ": True,
        }
        self.assertTrue(rds._eligible_start_stop(resource))
        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "Engine": "sqlserver-ee",
            "MultiAZ": True,
        }
        self.assertFalse(rds._eligible_start_stop(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "Engine": "docdb"
        }
        self.assertFalse(rds._eligible_start_stop(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "Engine": "postgres",
            "ReadReplicaDBInstanceIdentifiers": ["sbbdevslave"],
        }
        self.assertFalse(rds._eligible_start_stop(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "Engine": "mysql",
            "ReadReplicaSourceDBInstanceIdentifier": "sbbdev",
        }
        self.assertFalse(rds._eligible_start_stop(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "Engine": "mysql",
            "DBClusterIdentifier": "my-aurora-cluster",
        }
        self.assertFalse(rds._eligible_start_stop(resource))

    def test_rds_db_instance_eligible_for_backup(self):
        resource = {"DBInstanceIdentifier": "ABC"}
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {"DBInstanceIdentifier": "ABC", "DBInstanceStatus": "funky"}
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {"DBInstanceIdentifier": "ABC", "DBInstanceStatus": "available"}
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "DBClusterIdentifier": "C1",
        }
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "ReadReplicaSourceDBInstanceIdentifier": "R1",
            "Engine": "postgres",
        }
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "Engine": "postgres",
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "Engine": "mysql",
            "EngineVersion": "5.5.1",
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "ReadReplicaSourceDBInstanceIdentifier": "R1",
            "Engine": "mysql",
            "EngineVersion": "5.5.1",
        }
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "ReadReplicaSourceDBInstanceIdentifier": "R1",
            "Engine": "mysql",
            "EngineVersion": "5.7.1",
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "ReadReplicaSourceDBInstanceIdentifier": "R1",
            "Engine": "mysql",
            "EngineVersion": "6.1.1",
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

    def test_rds_db_instance_eligible_for_final_snapshot(self):
        resource = {"DBInstanceIdentifier": "ABC"}
        self.assertTrue(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {"DBInstanceIdentifier": "ABC", "DBInstanceStatus": "available"}
        self.assertTrue(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {"DBInstanceIdentifier": "ABC", "DBInstanceStatus": "creating"}
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {"DBInstanceIdentifier": "ABC", "DBInstanceStatus": "failed"}
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            "DBInstanceIdentifier": "ABC", "DBInstanceStatus": "incompatible-restore"
        }
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            "DBInstanceIdentifier": "ABC", "DBInstanceStatus": "incompatible-network"
        }
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "ReadReplicaSourceDBInstanceIdentifier": "R1",
            "Engine": "mysql",
            "EngineVersion": "5.7.1",
        }
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            "DBInstanceIdentifier": "ABC",
            "DBInstanceStatus": "available",
            "ReadReplicaSourceDBInstanceIdentifier": "",
            "Engine": "mysql",
            "EngineVersion": "5.7.1",
        }
        self.assertTrue(rds._db_instance_eligible_for_final_snapshot(resource))

    def test_rds_db_subnetgroup_delete(self):
        session_factory = self.replay_flight_data("test_rdssubnetgroup_delete")

        policy = self.load_policy(
            {
                "name": "db-subnet-group-delete",
                "resource": "rds-subnet-group",
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertGreater(len(resources), 0, "Test should delete db subnetgroup")

    def test_rds_db_subnetgroup_unused(self):
        session_factory = self.replay_flight_data("test_rdssubnetgroup_unused")

        policy = self.load_policy(
            {
                "name": "db-subnet-group-unused",
                "resource": "rds-subnet-group",
                "filters": [
                    {'DBSubnetGroupName': 'not-used'},
                    {"type": "unused"}
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(len(resources), 1, "Resources should be unused")
        self.assertEqual(resources[0]['DBSubnetGroupName'], "not-used")

    def test_rds_modify_db(self):
        session_factory = self.replay_flight_data("test_rds_modify_db")
        p = self.load_policy(
            {
                "name": "rds-modify-db",
                "resource": "rds",
                "filters": [
                    {"DeletionProtection": True},
                    {"MasterUsername": "testtest"}
                ],
                "actions": [
                    {
                        "type": "modify-db",
                        "update": [
                            {
                                "property": 'DeletionProtection',
                                "value": False
                            }
                        ],
                        "immediate": True
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("rds")
        db_info = client.describe_db_instances(DBInstanceIdentifier="testtest")
        self.assertFalse(db_info["DBInstances"][0]["DeletionProtection"])

    def test_rds_modify_db_enable_cloudwatch(self):
        session_factory = self.replay_flight_data("test_rds_modify_db_enable_cloudwatch")
        p = self.load_policy(
            {
                "name": "rds-modify-enable-cloudwatch",
                "resource": "rds",
                "filters": [
                    {
                        "type": "value",
                        "key": "DBInstanceIdentifier",
                        "value": "database-2"
                    },
                    {
                        "type": "value",
                        "key": "EnabledCloudwatchLogsExports[]",
                        "value": [
                            "error"
                        ],
                        "op": "ni"
                    }
                ],
                "actions": [
                    {
                        "type": "modify-db",
                        "update": [
                            {
                                "property": 'CloudwatchLogsExportConfiguration',
                                "value": {
                                    'EnableLogTypes': [
                                        "error"
                                    ]
                                }
                            }
                        ],
                        "immediate": True
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("rds")
        db_info = client.describe_db_instances(DBInstanceIdentifier="database-2")
        self.assertIn('error', db_info["DBInstances"][0]["EnabledCloudwatchLogsExports"])

    def test_rds_modify_db_validation_monitoring_error(self):
        with self.assertRaises(PolicyValidationError) as err:
            self.load_policy({
                'name': 'enable-monitoring',
                'resource': 'rds',
                "actions": [
                    {
                        "type": "modify-db",
                        "update": [
                            {
                                "property": 'MonitoringInterval',
                                "value": 60
                            }
                        ],
                        "immediate": True
                    }
                ]})
        self.assertIn((
            'A MonitoringRoleARN value is required'),
            str(err.exception))

    def test_rds_modify_db_validation_cloudwatch_error(self):
        with self.assertRaises(PolicyValidationError) as err:
            self.load_policy({
                'name': 'enable-cloudwatch',
                'resource': 'rds',
                "actions": [
                    {
                        "type": "modify-db",
                        "update": [
                            {
                                "property": 'CloudwatchLogsExportConfiguration',
                                "value": [
                                    "error"
                                ]
                            }
                        ],
                        "immediate": True
                    }
                ]})
        self.assertIn((
            'EnableLogTypes or DisableLogTypes input list is required'),
            str(err.exception))

    def test_rds_modify_db_enable_perfinsights(self):
        session_factory = self.replay_flight_data("test_rds_modify_db_enable_perfinsights")
        p = self.load_policy(
            {
                "name": "rds-modify-enable-perfinsights",
                "resource": "rds",
                "filters": [
                    {
                        "type": "value",
                        "key": "DBInstanceIdentifier",
                        "value": "database-4"
                    },
                    {
                        "type": "value",
                        "key": "PerformanceInsightsEnabled",
                        "value": False
                    }
                ],
                "actions": [
                    {
                        "type": "modify-db",
                        "update": [
                            {
                                "property": "EnablePerformanceInsights",
                                "value": True
                            }
                        ],
                        "immediate": True
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("rds")
        db_info = client.describe_db_instances(DBInstanceIdentifier="database-4")
        self.assertTrue(db_info["DBInstances"][0]["PerformanceInsightsEnabled"])

    def test_rds_snapshot_count_filter(self):
        factory = self.replay_flight_data("test_rds_snapshot_count_filter")
        p = self.load_policy(
            {
                "name": "rds-snapshot-count-filter",
                "resource": "rds",
                "filters": [{"type": "consecutive-snapshots", "days": 2}],
            },
            session_factory=factory,
        )
        with mock_datetime_now(parser.parse("2022-03-30T00:00:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_with_query_parameter(self):
        factory = self.replay_flight_data("test_rds_with_query_parameter")
        p = self.load_policy(
            {
                "name": "rds-with-query-parameter",
                "resource": "rds",
                "query": [{"Filters": [{"Name": "engine", "Values": ["mariadb"]}]}],
            },
            config={"region": "us-west-2"},
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_db_option_groups(self):
        session_factory = self.replay_flight_data("test_rds_db_option_groups")
        p = self.load_policy(
            {
                "name": "rds-data-in-transit-encrypt",
                "resource": "rds",
                "filters": [
                    {
                        "type": "db-option-groups",
                        "key": "Options[].OptionName",
                        "value": "NATIVE_NETWORK_ENCRYPTION",
                        "op": "contains"
                    }
                ],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBInstanceIdentifier"], "database-2")

    def test_rds_pending_maintenance(self):
        session_factory = self.replay_flight_data("test_rds_pending_maintenance")
        p = self.load_policy(
            {
                "name": "rds-pending-maintenance",
                "resource": "rds",
                "query": [
                    {
                        "DBInstanceIdentifier": "asset-sync-instance-1"
                    }
                ],
                "filters": [
                    {
                        "type": "value",
                        "key": "DBInstanceIdentifier",
                        "value": "asset-sync-instance-1"
                    },
                    {
                        "type": "pending-maintenance"
                    },
                    {
                        "type": "value",
                        "key": '"c7n:PendingMaintenance"[].PendingMaintenanceActionDetails['
                               '].Action',
                        "op": "intersect",
                        "value": ["system-update"]
                    }
                ],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)


def test_rds_snapshot_instance(test):
    factory = test.replay_flight_data('test_rds_snapshot_instance')
    p = test.load_policy(
        {'name': 'check-instance',
         'resource': 'aws.rds-snapshot',
         'filters': [
             {'type': 'instance',
              'key': 'DeletionProtection',
              'value': False}]},
        session_factory=factory)
    resources = p.run()
    assert len(resources) == 1
    resources[0]['DBSnapshotIdentifier'] == 'manual-testx'


class RDSSnapshotTest(BaseTest):

    def test_rds_snapshot_copy_tags_enable(self):
        session_factory = self.replay_flight_data("test_rds_snapshot_copy_tags_enable")
        client = session_factory(region="us-east-1").client("rds")
        self.assertFalse(
            client.describe_db_instances(DBInstanceIdentifier="mydbinstance")[
                "DBInstances"
            ][
                0
            ][
                "CopyTagsToSnapshot"
            ]
        )

        p = self.load_policy(
            {
                "name": "rds-enable-snapshot-tag-copy",
                "resource": "rds",
                "filters": [
                    {"type": "value", "key": "Engine", "value": "mysql", "op": "eq"}
                ],
                "actions": [{"type": "set-snapshot-copy-tags", "enable": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBInstanceIdentifier"], "mydbinstance")

        self.assertTrue(
            client.describe_db_instances(DBInstanceIdentifier="mydbinstance")[
                "DBInstances"
            ][
                0
            ][
                "CopyTagsToSnapshot"
            ]
        )

        self.assertDeprecation(p, """
            policy 'rds-enable-snapshot-tag-copy'
              actions:
                set-snapshot-copy-tags: action has been deprecated (use modify-db instead with `CopyTagsToSnapshot`)
            """)  # noqa: E501

    def test_rds_snapshot_copy_tags_disable(self):
        session_factory = self.replay_flight_data("test_rds_snapshot_copy_tags_disable")
        client = session_factory(region="us-east-1").client("rds")
        self.assertTrue(
            client.describe_db_instances(DBInstanceIdentifier="mydbinstance")[
                "DBInstances"
            ][
                0
            ][
                "CopyTagsToSnapshot"
            ]
        )

        p = self.load_policy(
            {
                "name": "rds-enable-snapshot-tag-copy",
                "resource": "rds",
                "filters": [
                    {"type": "value", "key": "Engine", "value": "mysql", "op": "eq"}
                ],
                "actions": [{"type": "set-snapshot-copy-tags", "enable": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBInstanceIdentifier"], "mydbinstance")

        self.assertFalse(
            client.describe_db_instances(DBInstanceIdentifier="mydbinstance")[
                "DBInstances"
            ][
                0
            ][
                "CopyTagsToSnapshot"
            ]
        )

    def test_rds_snapshot_access(self):
        factory = self.replay_flight_data("test_rds_snapshot_access")
        p = self.load_policy(
            {
                "name": "rds-snap-access",
                "resource": "rds-snapshot",
                "filters": ["cross-account"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            {
                r["DBSnapshotIdentifier"]: r["c7n:CrossAccountViolations"]
                for r in resources
            },
            {"tidx-pub": ["all"], "tidx-rdx": ["619193117841"]},
        )

    def test_rds_snapshot_access_everyone_only(self):
        factory = self.replay_flight_data("test_rds_snapshot_access")
        p = self.load_policy(
            {
                "name": "rds-snap-access",
                "resource": "rds-snapshot",
                "filters": [{
                    "type": "cross-account",
                    "everyone_only": True,
                }],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {
                r["DBSnapshotIdentifier"]: r["c7n:CrossAccountViolations"]
                for r in resources
            },
            {"tidx-pub": ["all"]},
        )

    def test_rds_latest_manual(self):
        # preconditions
        # one db with manual and automatic snapshots
        factory = self.replay_flight_data("test_rds_snapshot_latest")
        p = self.load_policy(
            {
                "name": "rds-latest-snaps",
                "resource": "rds-snapshot",
                "filters": [{"type": "latest", "automatic": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBSnapshotIdentifier"], "originb")

    def test_rds_latest(self):
        # preconditions
        # one db with manual and automatic snapshots
        factory = self.replay_flight_data("test_rds_snapshot_latest")
        p = self.load_policy(
            {
                "name": "rds-latest-snaps",
                "resource": "rds-snapshot",
                "filters": ["latest"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["DBSnapshotIdentifier"], "rds:originb-2016-12-28-09-15"
        )

    def test_rds_cross_region_copy_lambda(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "rds-copy-fail",
                "resource": "rds-snapshot",
                "mode": {"type": "config-rule"},
                "actions": [{"type": "region-copy", "target_region": "us-east-2"}],
            },
        )

    def test_rds_cross_region_copy_skip_same_region(self):
        factory = self.replay_flight_data("test_rds_snapshot_latest")
        output = self.capture_logging("custodian.actions")
        p = self.load_policy(
            {
                "name": "rds-copy-skip",
                "resource": "rds-snapshot",
                "actions": [{"type": "region-copy", "target_region": "us-east-2"}],
            },
            config={'region': 'us-east-2'},
            session_factory=factory,
        )
        resources = p.run()
        self.assertFalse([r for r in resources if "c7n:CopiedSnapshot" in r])
        self.assertIn("Source and destination region are the same", output.getvalue())

    def test_rds_cross_region_copy_many(self):
        # preconditions
        # rds snapshot, encrypted in region with kms, and tags
        # in this scenario we have 9 snapshots in source region,
        # 3 snaps already in target region, 6 to copy, which means
        # we will hit transfer limits.
        factory = self.replay_flight_data("test_rds_snapshot_region_copy_many")

        # no sleep till, beastie boys ;-)
        def brooklyn(delay):
            return

        output = self.capture_logging("c7n.retry", level=logging.DEBUG)
        self.patch(time, "sleep", brooklyn)
        self.change_environment(AWS_DEFAULT_REGION="us-east-1")
        p = self.load_policy(
            {
                "name": "rds-snapshot-region-copy",
                "resource": "rds-snapshot",
                "filters": [{"DBInstanceIdentifier": "originb"}],
                "actions": [
                    {
                        "type": "region-copy",
                        "target_region": "us-east-2",
                        "tags": {"migrated_from": "us-east-1"},
                        "target_key": "cb291f53-f3ab-4e64-843e-47b0a7c9cf61",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 9)
        self.assertEqual(6, len([r for r in resources if "c7n:CopiedSnapshot" in r]))
        self.assertEqual(output.getvalue().count("retrying"), 2)

    def test_rds_cross_region_copy(self):
        # preconditions
        # rds snapshot, encrypted in region with kms, and tags
        factory = self.replay_flight_data("test_rds_snapshot_region_copy")
        client = factory().client("rds", region_name="us-east-2")
        self.change_environment(AWS_DEFAULT_REGION="us-east-1")
        p = self.load_policy(
            {
                "name": "rds-snapshot-region-copy",
                "resource": "rds-snapshot",
                "filters": [{"DBSnapshotIdentifier": "rds:originb-2016-12-28-09-15"}],
                "actions": [
                    {
                        "type": "region-copy",
                        "target_region": "us-east-2",
                        "tags": {"migrated_from": "us-east-1"},
                        "target_key": "cb291f53-f3ab-4e64-843e-47b0a7c9cf61",
                    }
                ],
            },
            config=dict(region="us-east-1"),
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        snapshots = client.describe_db_snapshots(
            DBSnapshotIdentifier=resources[0]["c7n:CopiedSnapshot"].rsplit(":", 1)[1]
        )[
            "DBSnapshots"
        ]
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["DBInstanceIdentifier"], "originb")
        tags = {
            t["Key"]: t["Value"]
            for t in client.list_tags_for_resource(
                ResourceName=resources[0]["c7n:CopiedSnapshot"]
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

    def test_rds_snapshot_tag_filter(self):
        factory = self.replay_flight_data("test_rds_snapshot_tag_filter")
        client = factory().client("rds")
        p = self.load_policy(
            {
                "name": "rds-snapshot-tag-filter",
                "resource": "rds-snapshot",
                "filters": [{"type": "marked-for-op", "op": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(resources[0]["DBSnapshotIdentifier"])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("maid_status" in tag_map)
        self.assertTrue("delete@" in tag_map["maid_status"])

    def test_rds_snapshot_age_filter(self):
        factory = self.replay_flight_data("test_rds_snapshot_age_filter")
        p = self.load_policy(
            {
                "name": "rds-snapshot-age-filter",
                "resource": "rds-snapshot",
                "filters": [{"type": "age", "days": 7}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_snapshot_trim(self):
        factory = self.replay_flight_data("test_rds_snapshot_delete")
        p = self.load_policy(
            {
                "name": "rds-snapshot-trim",
                "resource": "rds-snapshot",
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @mock.patch("c7n.resources.rds.RDSSnapshotDelete.process_snapshot_set")
    def test_rds_snapshot_trim_skip_automated(self, process_snapshot_set):
        factory = self.replay_flight_data("test_rds_snapshot_delete_skip_automated",
            region="us-east-2")
        log_output = self.capture_logging('custodian.actions')
        p = self.load_policy(
            {
                "name": "rds-snapshot-trim-skip-automated",
                "resource": "rds-snapshot",
                "filters": [
                    {
                        "DBInstanceIdentifier": "c7n-test"
                    },
                    {
                        "type": "reduce",
                        "group-by": "SnapshotType",
                        "sort-by": "SnapshotCreateTime",
                        "limit": 1
                    }
                ],
                "actions": ["delete"],
            },
            session_factory=factory,
            config={"region": "us-east-2"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        assert (
            'delete implicitly filtered 1 of 2 resources'
            in log_output.getvalue().strip()
        )
        assert process_snapshot_set.call_count == 1

    @mock.patch("c7n.resources.rds.RDSSnapshotDelete.process_snapshot_set")
    def test_rds_snapshot_trim_skip_automated_noop(self, process_snapshot_set):
        factory = self.replay_flight_data("test_rds_snapshot_delete_skip_automated",
            region="us-east-2")
        log_output = self.capture_logging('custodian.actions')
        p = self.load_policy(
            {
                "name": "rds-snapshot-trim-skip-automated-noop",
                "resource": "rds-snapshot",
                "filters": [
                    {
                        "DBInstanceIdentifier": "c7n-test"
                    },
                    {
                        "SnapshotType": "automated"
                    },
                    {
                        "type": "reduce",
                        "sort-by": "SnapshotCreateTime",
                        "limit": 1
                    }
                ],
                "actions": ["delete"],
            },
            session_factory=factory,
            config={"region": "us-east-2"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        assert (
            'delete implicitly filtered 0 of 1 resources'
            in log_output.getvalue().strip()
        )
        assert process_snapshot_set.call_count == 0

    def test_rds_snapshot_tag(self):
        factory = self.replay_flight_data("test_rds_snapshot_mark")
        client = factory().client("rds")
        p = self.load_policy(
            {
                "name": "rds-snapshot-tag",
                "resource": "rds-snapshot",
                "actions": [{"type": "tag", "key": "test-key", "value": "test-value"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(resources[0]["DBSnapshotIdentifier"])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("test-key" in tag_map)
        self.assertTrue("test-value" in tag_map["test-key"])

    def test_rds_snapshot_mark(self):
        factory = self.replay_flight_data("test_rds_snapshot_mark")
        client = factory().client("rds")
        p = self.load_policy(
            {
                "name": "rds-snapshot-mark",
                "resource": "rds-snapshot",
                "actions": [{"type": "mark-for-op", "op": "delete", "days": 1}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(resources[0]["DBSnapshotIdentifier"])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("maid_status" in tag_map)

    def test_rds_snapshot_unmark(self):
        factory = self.replay_flight_data("test_rds_snapshot_unmark")
        client = factory().client("rds")
        p = self.load_policy(
            {
                "name": "rds-snapshot-unmark",
                "resource": "rds-snapshot",
                "actions": [{"type": "unmark"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(resources[0]["DBSnapshotIdentifier"])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertFalse("maid_status" in tag_map)

    def test_rds_public_accessible_disable(self):
        session_factory = self.replay_flight_data("test_rds_public_accessible_disable")
        client = session_factory(region="us-east-1").client("rds")
        policy = self.load_policy(
            {
                "name": "disable-publicly-accessibility",
                "resource": "rds",
                "filters": [
                    {"DBInstanceIdentifier": "c7n-test-pa"},
                    {"PubliclyAccessible": True},
                ],
                "actions": [{"type": "set-public-access", "state": False}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBInstanceIdentifier"], "c7n-test-pa")
        self.assertFalse(
            client.describe_db_instances(DBInstanceIdentifier="c7n-test-pa")[
                "DBInstances"
            ][
                0
            ][
                "PubliclyAccessible"
            ]
        )

    def _get_effective_permissions(self, client, snapshot_id):
        attributes = client.describe_db_snapshot_attributes(
            DBSnapshotIdentifier=snapshot_id
        )["DBSnapshotAttributesResult"]["DBSnapshotAttributes"]
        attr_map = {
            attr["AttributeName"]: attr["AttributeValues"]
            for attr in attributes
        }
        return set(attr_map.get("restore", []))

    def test_set_permissions(self):
        session_factory = self.replay_flight_data(
            "test_rds_snapshot_set_permissions",
            region="us-east-2"
        )
        target_snapshot_id = "testing"
        keep = "644160558196"
        remove = "123456789012"
        add = "234567890123"
        policy = self.load_policy(
            {
                "name": "rds-snapshot-remove-permissions",
                "resource": "rds-snapshot",
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
            "test_rds_snapshot_remove_matched_permissions",
            region="us-east-2"
        )
        target_snapshot_id = "testing"
        keep = "644160558196"
        remove = "123456789012"
        policy = self.load_policy(
            {
                "name": "rds-snapshot-remove-matched-permissions",
                "resource": "rds-snapshot",
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
            resources[0]["DBSnapshotIdentifier"]
        )
        self.assertIn(keep, restore_permissions_after)
        self.assertNotIn(remove, restore_permissions_after)

    def test_clear_permissions(self):
        session_factory = self.replay_flight_data(
            "test_rds_snapshot_clear_permissions",
            region="us-east-2"
        )
        target_snapshot_id = "testing"
        policy = self.load_policy(
            {
                "name": "rds-snapshot-clear-permissions",
                "resource": "rds-snapshot",
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
            resources[0]["DBSnapshotIdentifier"]
        )
        self.assertEqual(len(restore_permissions_after), 0)

    def test_set_permissions_invalid(self):
        with self.assertRaises(PolicyValidationError) as err:
            self.load_policy(
                {
                    "name": "rds-snapshot-set-permissions-invalid",
                    "resource": "rds-snapshot",
                    "actions": [
                        {"type": "set-permissions", "remove": "matched"}
                    ]
                },
            )
        self.assertIn("requires cross-account filter", str(err.exception))

    def test_rds_engine_filter(self):
        session_factory = self.replay_flight_data("test_rds_engine_filter")
        p = self.load_policy(
            {
                "name": "rds-engine-filter",
                "resource": "aws.rds",
                "filters": [
                    {
                        "type": "engine",
                        "key": "Status",
                        "value": "available"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("c7n:Engine" in resources[0].keys())

    def test_rds_consecutive_aws_backups_count_filter(self):
        session_factory = self.replay_flight_data("test_rds_consecutive_aws_backups_count_filter")
        p = self.load_policy(
            {
                "name": "rds_consecutive_aws_backups_count_filter",
                "resource": "rds",
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

    def test_rds_snapshot_copy_related_tags(self):
        factory = self.replay_flight_data("test_rds_snapshot_copy_related_tags")
        client = factory().client("rds")
        p = self.load_policy(
            {
                "name": "rds-snapshot-copy-related-tags",
                "resource": "rds-snapshot",
                "filters": [{"tag:Owner": "absent"}],
                "actions": [
                    {
                        "type": "copy-related-tag",
                        "key": "DBInstanceIdentifier",
                        "resource": "rds",
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
        for resource in resources:
            arn = p.resource_manager.generate_arn(resource["DBSnapshotIdentifier"])
            tags = client.list_tags_for_resource(ResourceName=arn)
            tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
            self.assertTrue("Owner" in tag_map)


class TestModifyVpcSecurityGroupsAction(BaseTest):

    def test_rds_remove_matched_security_groups(self):
        #
        # Test conditions:
        #    - running 2 Aurora DB clusters in default VPC with 2 instances
        #      each.
        #        - translates to 4 actual instances
        #    - a default security group with id 'sg-7a3fcb13' exists
        #    - security group named PROD-ONLY-Test-Security-Group exists in
        #      VPC and is attached to one set of DB instances
        #        - translates to 2 instances marked non-compliant
        #
        # Results in 4 DB Instances with default Security Group attached

        session_factory = self.replay_flight_data(
            "test_rds_remove_matched_security_groups"
        )
        p = self.load_policy(
            {
                "name": "rds-remove-matched-security-groups",
                "resource": "rds",
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
                "name": "rds-verify-remove-matched-security-groups",
                "resource": "rds",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        clean_resources = clean_p.run()

        # clusters autoscale across AZs, so they get -001, -002, etc appended
        self.assertIn("test-sg-fail", resources[0]["DBInstanceIdentifier"])

        self.assertEqual(len(resources), 2)
        self.assertEqual(len(resources[0]["VpcSecurityGroups"]), 1)
        # show that it was indeed a replacement of security groups
        self.assertEqual(len(clean_resources[0]["VpcSecurityGroups"]), 1)
        self.assertEqual(len(clean_resources), 4)

    def test_rds_add_security_group(self):
        #
        # Test conditions:
        #   - running 2 Aurora DB clusters in default VPC with 2 instances each
        #        - translates to 4 actual instances
        #    - a default security group with id 'sg-7a3fcb13' exists -
        #      attached to all instances
        #    - security group named PROD-ONLY-Test-Security-Group exists in
        #      VPC and is attached to 2/4 instances
        #        - translates to 2 instances marked to get new group attached
        #
        # Results in 4 instances with default Security Group and
        # PROD-ONLY-Test-Security-Group
        session_factory = self.replay_flight_data("test_rds_add_security_group")
        p = self.load_policy(
            {
                "name": "add-sg-to-prod-rds",
                "resource": "rds",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"},
                    {
                        "type": "value",
                        "key": "DBInstanceIdentifier",
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
                "name": "validate-add-sg-to-prod-rds",
                "resource": "rds",
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

        self.assertEqual(len(resources), 2)
        self.assertIn("test-sg-fail", resources[0]["DBInstanceIdentifier"])
        self.assertEqual(len(resources[0]["VpcSecurityGroups"]), 1)
        self.assertEqual(len(clean_resources[0]["VpcSecurityGroups"]), 2)
        self.assertEqual(len(clean_resources), 4)

    def test_rds_filter_by_vpcid(self):
        #
        # Test conditions:
        # Purpose of test is only to validate checking vpc filtered ID with DBSubnetGroup.VpcId
        # Uses the add_security_group data--should match 4 DB instances (all in the filtered VPC)
        # Checks that the expected VPC is present

        session_factory = self.replay_flight_data("test_rds_add_security_group")
        p = self.load_policy(
            {
                "name": "filter-by-vpcid",
                "resource": "rds",
                "filters": [
                    {
                        "type": "vpc",
                        "key": "VpcId",
                        "value": "vpc-09b75e60",
                        "op": "eq",
                    },
                ],
                "actions": [{"type": "modify-security-groups", "add": "sg-6360920a"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 4)
        self.assertEqual("vpc-09b75e60", resources[0]["DBSubnetGroup"]["VpcId"])

    def test_rds_sg_add_by_tag(self):
        session_factory = self.replay_flight_data("test_rds_sg_add_by_tag")
        client = session_factory().client('rds')
        policy = self.load_policy({
            "name": "add-sg-via-tags",
            "resource": "rds",
                "filters": [
                    {"type": "security-group", "key": "tag:c7n", "value": "add", "op": "ne"}],
            "actions": [
                {"type": "modify-security-groups",
                 "add-by-tag": {
                      "key": "c7n",
                      "values": ["add"]}}]},
            session_factory=session_factory,
        )
        resources = policy.run()
        if self.recording:
            time.sleep(60)
        self.assertEqual(len(resources), 1)
        self.assertAlmostEqual(
            len(resources[0]['VpcSecurityGroups']), 1)
        db = client.describe_db_instances(DBInstanceIdentifier="database-1")
        mod_sgs = db.get('DBInstances')[0].get('VpcSecurityGroups')
        self.assertTrue(len(mod_sgs), 2)


class TestHealthEventsFilter(BaseTest):

    def test_rds_health_events_filter(self):
        session_factory = self.replay_flight_data("test_rds_health_events_filter")
        policy = self.load_policy(
            {
                "name": "rds-health-events-filter",
                "resource": "rds",
                "filters": [{"type": "health-event"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 0)


class TestRDSParameterGroupFilter(BaseTest):

    PARAMGROUP_PARAMETER_FILTER_TEST_CASES = [
        # filter_struct, test_func, err_message
        (
            {"key": "log_destination", "op": "eq", "value": "stderr"},
            lambda r: len(r) == 1,
            "instances with log_destination == stderr should be 1",
        ),
        (
            {"key": "log_destination", "op": "eq", "value": "s3"},
            lambda r: len(r) == 0,
            "instances with log_destination == s3 should be 0",
        ),
        (
            {"key": "log_destination", "op": "ne", "value": "stderr"},
            lambda r: len(r) == 0,
            "instances with log_destination != stderr should be 0",
        ),
        (
            {"key": "log_destination", "op": "ne", "value": "s3"},
            lambda r: len(r) == 1,
            "instances with log_destination != s3 should be 1",
        ),
        (
            {"key": "full_page_writes", "op": "eq", "value": True},
            lambda r: len(r) == 1,
            "full_page_writes ( a boolean ) should be on",
        ),
    ]

    def test_param_value_cases(self):
        session_factory = self.replay_flight_data("test_rds_param_filter")
        policy = self.load_policy(
            {"name": "rds-pg-filter", "resource": "rds"},
            session_factory=session_factory,
        )
        resources = policy.resource_manager.resources()

        for testcase in self.PARAMGROUP_PARAMETER_FILTER_TEST_CASES:
            fdata, assertion, err_msg = testcase
            f = policy.resource_manager.filter_registry.get("db-parameter")(
                fdata, policy.resource_manager
            )
            f_resources = f.process(resources)
            if not assertion(f_resources):
                print(len(f_resources), fdata, assertion)
                self.fail(err_msg)

    def test_rds_param_value(self):
        session_factory = self.replay_flight_data("test_rds_param_value")
        p = self.load_policy(
            {
                "name": "rds-param-value",
                "resource": "aws.rds",
                "filters": [
                    {
                        "type": "db-parameter",
                        "key": "rds.force_admin_logging_level",
                        "value": "info",
                        "value_type": "normalize",
                        "op": "eq",
                    },
                ],
            },
            session_factory=session_factory, cache=True,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get('DBInstanceIdentifier'), 'c7n-test')
        self.assertEqual(resources[0].get(
            'c7n:MatchedDBParameter')[0], 'rds.force_admin_logging_level')
        self.assertIn(('DBParameterGroupName', 'test'), resources[0].get(
            'DBParameterGroups')[0].items())


class Resize(BaseTest):

    def get_waiting_client(self, session_factory, session, name):
        if session_factory.__name__ == "<lambda>":  # replaying
            return None
        else:  # recording
            return boto3.Session(region_name=session.region_name).client(name)

    def get_dbid(self, recording, flight_data):
        if recording:
            return "test-" + str(uuid.uuid4())
        else:
            pill_path = os.path.join(
                os.path.dirname(__file__),
                "data",
                "placebo",
                flight_data,
                "rds.CreateDBInstance_1.json",
            )
            pill = json.load(open(pill_path))
            return pill["data"]["DBInstance"]["DBInstanceIdentifier"]

    def install_modification_pending_waiter(self, waiters):
        if "DBInstanceModificationPending" in waiters:
            return
        pattern = waiters["DBInstanceAvailable"]
        acceptors = [OrderedDict(eg) for eg in pattern["acceptors"][1:]]
        acceptors.insert(
            0,
            OrderedDict(
                expected=True,
                matcher="path",
                state="success",
                argument="!!length(DBInstances[].PendingModifiedValues)",
            ),
        )
        waiter = OrderedDict(pattern)
        waiter["acceptors"] = acceptors
        waiters["DBInstanceModificationPending"] = waiter

    def install_modifying_waiter(self, waiters):
        if "DBInstanceModifying" in waiters:
            return
        pattern = waiters["DBInstanceAvailable"]
        acceptors = [OrderedDict(eg) for eg in pattern["acceptors"]]
        acceptors[0]["expected"] = "modifying"
        waiter = OrderedDict(pattern)
        waiter["acceptors"] = acceptors
        waiters["DBInstanceModifying"] = waiter

    def install_waiters(self, client):
        # Not provided by boto otb.
        client._get_waiter_config()  # primes cache if needed
        waiters = client._cache["waiter_config"]["waiters"]
        self.install_modification_pending_waiter(waiters)
        self.install_modifying_waiter(waiters)

    def wait_until(self, client, dbid, status):
        if client is None:
            return  # We're in replay mode. Don't bother waiting.
        self.install_waiters(client)
        waiter = client.get_waiter("db_instance_" + status)
        waiter.wait(Filters=[{"Name": "db-instance-id", "Values": [dbid]}])

    def create_instance(self, client, dbid, gb=5):
        client.create_db_instance(
            Engine="mariadb",
            DBInstanceIdentifier=dbid,
            DBInstanceClass="db.r3.large",
            MasterUsername="eric",
            MasterUserPassword="cheese42",
            StorageType="gp2",
            AllocatedStorage=gb,
            BackupRetentionPeriod=0,
        )  # disable automatic backups

        def delete():
            client.delete_db_instance(DBInstanceIdentifier=dbid, SkipFinalSnapshot=True)

        self.addCleanup(delete)
        return dbid

    @staticmethod
    def get_window_now():
        start = datetime.datetime.utcnow()
        end = start + datetime.timedelta(seconds=60 * 60)  # hour long
        fmt = "%a:%H:%M"
        return "{}-{}".format(start.strftime(fmt), end.strftime(fmt))

    def test_can_get_a_window_now(self):
        assert re.match(r"[A-Za-z]{3}:\d\d:\d\d", self.get_window_now())

    def start(self, flight_data):
        session_factory = self.replay_flight_data(flight_data)
        session = session_factory(region="us-west-2")
        client = session.client("rds")
        waiting_client = self.get_waiting_client(session_factory, session, "rds")
        dbid = self.get_dbid(bool(waiting_client), flight_data)
        self.create_instance(client, dbid)

        wait_until = lambda state: self.wait_until(waiting_client, dbid, state) # NOQA
        wait_until("available")

        describe = lambda: client.describe_db_instances(DBInstanceIdentifier=dbid)[ # NOQA
            "DBInstances"
        ][
            0
        ]

        def resize(**kw):
            action = {"type": "resize", "percent": 10}
            action.update(kw)
            policy = self.load_policy(
                {
                    "name": "rds-resize-up",
                    "resource": "rds",
                    "filters": [
                        {"type": "value", "key": "DBInstanceIdentifier", "value": dbid}
                    ],
                    "actions": [action],
                },
                config={"region": "us-west-2"},
                session_factory=session_factory,
            )
            policy.run()

        return client, dbid, resize, wait_until, describe

    def test_can_resize_up_asynchronously(self):
        flight = "test_rds_resize_up_asynchronously"
        client, dbid, resize, wait_until, describe = self.start(flight)
        resize()
        wait_until("modification_pending")
        client.modify_db_instance(
            DBInstanceIdentifier=dbid, PreferredMaintenanceWindow=self.get_window_now()
        )
        wait_until("modifying")
        wait_until("available")
        self.assertEqual(describe()["AllocatedStorage"], 6)  # nearest gigabyte

    def test_can_resize_up_immediately(self):
        flight = "test_rds_resize_up_immediately"
        _, _, resize, wait_until, describe = self.start(flight)
        resize(immediate=True)
        wait_until("modifying")
        wait_until("available")
        self.assertEqual(describe()["AllocatedStorage"], 6)  # nearest gigabyte


class TestReservedRDSInstance(BaseTest):
    def test_reserved_rds_instance_query(self):
        session_factory = self.replay_flight_data("test_reserved_rds_instance_query")
        p = self.load_policy(
            {
                "name": "filter-rds-reserved-instances",
                "resource": "aws.rds-reserved"
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ReservedDBInstanceId"], "ri-2019-05-06-14-19-06-332")


class RDSEventSubscription(BaseTest):
    def test_rds_event_subscription_delete(self):
        session_factory = self.replay_flight_data("test_rds_event_subscription_delete")
        p = self.load_policy(
            {
                "name": "rds-event-subscription-delete",
                "resource": "aws.rds-subscription",
                "filters": [{"type": "value", "key": "tag:name", "value": "pratyush"}],
                "actions": [{"type": "delete"}]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["CustSubscriptionId"], "c7n-test-pratyush")
        client = session_factory().client("rds")
        response = client.describe_event_subscriptions()
        self.assertEqual(len(response.get('EventSubscriptionsList')), 0)

    def test_rds_event_subscription_topic_filter(self):
        session_factory = self.replay_flight_data("test_rds_event_subscription_topic_filter")
        p = self.load_policy({
            "name": "rds-subscriptions-no-confirmed-topics",
            "resource": "aws.rds-subscription",
            "filters": [{
                "type": "topic",
                "key": "SubscriptionsConfirmed",
                "value": 0,
                "value_type": "integer"
            }],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:SnsTopic"]["SubscriptionsConfirmed"], "0")


class TestRDSParameterGroupFilterModified(BaseTest):
    def test_param_filter_value_cases(self):
        session_factory = self.replay_flight_data('test_rds_parameter_group')
        policy = self.load_policy(
            {
                "name": "rds-paramter-group-test",
                "resource": "rds",
                "filters": [
                    {
                        "type": "db-parameter",
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


class RDSProxy(BaseTest):
    def test_rds_proxy_resource(self):
        session_factory = self.replay_flight_data('test_rds_proxy_resource')
        p = self.load_policy(
            {
                'name': 'test-rds-proxy',
                'resource': 'rds-proxy',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'RequireTLS',
                        'value': False
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DBProxyName'], 'test-us-east-1-db-proxy')
        self.assertEqual(resources[0]['RequireTLS'], False)

    def test_rds_proxy_delete(self):
        session_factory = self.replay_flight_data('test_rds_proxy_delete')
        p = self.load_policy(
            {
                'name': 'delete-rds-proxy',
                'resource': 'aws.rds-proxy',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'DBProxyName',
                        'value': 'proxy-test-1'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete'
                    }
                ],
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('rds')
        resources = client.describe_db_proxies()
        self.assertEqual(resources['DBProxies'][0]['DBProxyName'], 'proxy-test-1')
        self.assertEqual(resources['DBProxies'][0]['Status'], 'deleting')

    def test_rds_proxy_subnet_filter(self):
        session_factory = self.replay_flight_data("test_rds_proxy_subnet_filter")
        p = self.load_policy(
            {
                "name": "rds-proxy-subnet-filter",
                "resource": "rds-proxy",
                "filters": [
                    {
                        "type": "subnet",
                        "key": "DefaultForAz",
                        "op": "eq",
                        "value": False,
                    }
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBProxyName"], "proxy-test-1")

    def test_rds_proxy_security_group_filter(self):
        session_factory = self.replay_flight_data("test_rds_proxy_security_group_filter")
        p = self.load_policy(
            {
                "name": "rds-proxy-security-group-filter",
                "resource": "rds-proxy",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "tag:ASV",
                        "op": "eq",
                        "value": "PolicyTest",
                    }
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBProxyName"], "proxy-test-1")

    def test_rds_proxy_vpc_filter(self):
        session_factory = self.replay_flight_data("test_rds_proxy_vpc_filter")
        p = self.load_policy(
            {
                "name": "rds-proxy-vpc-filter",
                "resource": "rds-proxy",
                "filters": [
                    {
                        "type": "vpc",
                        "key": "tag:Name",
                        "op": "eq",
                        "value": "DemoVPC",
                    }
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DBProxyName"], "proxy-test-1")


@terraform('rds_delete_aurora_filter')
def test_rds_delete_logs_aurora_filter(test, rds_delete_aurora_filter):
    session_factory = test.replay_flight_data('test_rds_delete_aurora_filter')

    output = test.capture_logging('custodian.actions', level=logging.WARNING)

    p = test.load_policy(
        {
            'name': 'rds-delete-aurora',
            'resource': 'rds',
            'filters': [
                {'DBInstanceIdentifier': 'aurora-test-instance'}
            ],
            'actions': [
                {'type': 'delete', 'skip-snapshot': True}
            ],
        },
        session_factory=session_factory
    )

    p.run()

    log_text = output.getvalue()
    test.assertEqual(
        log_text.strip(),
        'delete implicitly filtered 0 of 1 resources key:DBClusterIdentifier on None',
    )
