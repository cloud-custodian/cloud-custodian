# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
import datetime
from dateutil import tz as tzutil
from unittest.mock import MagicMock
from c7n.testing import mock_datetime_now
from dateutil import parser

import c7n.resources.dynamodb
import c7n.filters.backup
from c7n.resources.dynamodb import DeleteTable
from c7n.executor import MainThreadExecutor


class DynamodbTest(BaseTest):

    def test_resources(self):
        session_factory = self.replay_flight_data("test_dynamodb_table")
        p = self.load_policy(
            {"name": "tables", "resource": "dynamodb-table"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["TableName"], "test-table-kms-filter")
        self.assertEqual(resources[0]["TableStatus"], "ACTIVE")

    def test_invoke_action(self):
        session_factory = self.replay_flight_data("test_dynamodb_invoke_action")
        p = self.load_policy(
            {
                "name": "tables",
                "resource": "dynamodb-table",
                "actions": [{"type": "invoke-lambda", "function": "process_resources"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_tables(self):
        session_factory = self.replay_flight_data("test_dynamodb_delete_table")
        self.patch(DeleteTable, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "delete-empty-tables",
                "resource": "dynamodb-table",
                "filters": [{"TableSizeBytes": 0}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["TableName"], "c7n.DynamoDB.01")

    def test_force_delete_dynamodb_tables(self):
        session_factory = self.replay_flight_data("test_force_delete_dynamodb_tables")
        client = session_factory().client("dynamodb")
        self.patch(DeleteTable, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "delete-empty-tables",
                "resource": "dynamodb-table",
                "filters": [{"TableName": "c7n-test"}],
                "actions": [
                    {
                        "type": "delete",
                        "force": True
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["DeletionProtectionEnabled"], True)
        table = client.describe_table(TableName="c7n-test")["Table"]
        self.assertEqual(table.get('TableStatus'), 'DELETING')

    def test_update_tables(self):
        session_factory = self.replay_flight_data("test_dynamodb_update_table")
        client = session_factory().client("dynamodb")
        p = self.load_policy(
            {
                "name": "update-empty-tables",
                "resource": "dynamodb-table",
                "actions": [{"type": "update", "BillingMode": "PAY_PER_REQUEST"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        assert resources[0]["TableName"] == "cc-testing-table"
        t = client.describe_table(TableName="cc-testing-table")["Table"]
        assert t["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"

    def test_tag_filter(self):
        session_factory = self.replay_flight_data("test_dynamodb_tag_filter")
        client = session_factory().client("dynamodb")
        p = self.load_policy(
            {
                "name": "dynamodb-tag-filters",
                "resource": "dynamodb-table",
                "filters": [{"tag:test_key": "test_value"}],
            },
            session_factory=session_factory,
            config={'region': 'us-west-2', 'account_id': '644160558196'})

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["TableArn"]
        tags = client.list_tags_of_resource(ResourceArn=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["Tags"]}
        self.assertTrue("test_key" in tag_map)

    def test_kms_key_filter(self):
        session_factory = self.replay_flight_data("test_dynamodb_kms_key_filter")
        p = self.load_policy(
            {
                "name": "dynamodb-kms-key-filters",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "^(alias/aws/dynamodb)",
                        "op": "regex"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["TableName"], "test-table-kms-filter")

    def test_continuous_backup_filter(self):
        session_factory = self.replay_flight_data("test_dynamodb_continuous_backup_filter")
        p = self.load_policy(
            {
                "name": "dynamodb-continuous_backup-filters",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "continuous-backup",
                        "key": "PointInTimeRecoveryDescription.PointInTimeRecoveryStatus",
                        "value": "DISABLED",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["c7n:continuous-backup"]["PointInTimeRecoveryDescription"]["PointInTimeRecoveryStatus"], # noqa
            "DISABLED")

    def test_dynamodb_cross_account_filter(self):
        session_factory = self.replay_flight_data("test_dynamodb_cross_account_filter")
        p = self.load_policy(
            {
                "name": "dynamodb-cross-account",
                "resource": "dynamodb-table",
                "filters": ['cross-account'],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("c7n:Policy" in resources[0])

    def test_dynamodb_has_statement_filter(self):
        session_factory = self.replay_flight_data("test_dynamodb_has_statement_filter")
        p = self.load_policy(
            {
                "name": "dynamodb-has-statement",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": "dynamodb:*",
                                "Principal": "*",
                                "Condition":
                                    {"Bool": {"aws:SecureTransport": "false"}},
                                "Resource": "{table_arn}"
                            }
                        ]
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("c7n:Policy" in resources[0])

    def test_continuous_backup_action(self):
        session_factory = self.replay_flight_data("test_dynamodb_continuous_backup_action")
        client = session_factory().client("dynamodb")
        p = self.load_policy(
            {
                "name": "dynamodb-continuous_backup-action",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "continuous-backup",
                        "key": "PointInTimeRecoveryDescription.PointInTimeRecoveryStatus",
                        "value": "ENABLED",
                        "op": "ne"
                    }
                ],
                "actions": [
                    {
                        "type": "set-continuous-backup"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["c7n:continuous-backup"]["PointInTimeRecoveryDescription"]["PointInTimeRecoveryStatus"],  # noqa
            "DISABLED")
        res = client.describe_continuous_backups(TableName=resources[0]["TableName"])['ContinuousBackupsDescription']  # noqa
        self.assertEqual(
            res['PointInTimeRecoveryDescription']["PointInTimeRecoveryStatus"],
            'ENABLED')

    def test_continuous_backup_action_error(self):
        factory = self.replay_flight_data("test_dynamodb_continuous_backup_action")

        client = factory().client("dynamodb")
        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'
        mock_factory().client(
            'dynamodb').exceptions.TableNotFoundException = (
                client.exceptions.TableNotFoundException)

        mock_factory().client('dynamodb').update_continuous_backups.side_effect = (
            client.exceptions.TableNotFoundException(
                {'Error': {'Code': 'xyz'}},
                operation_name='update_continuous_backups'))
        p = self.load_policy(
            {
                "name": "dynamodb-continuous_backup-action",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "continuous-backup",
                        "key": "PointInTimeRecoveryDescription.PointInTimeRecoveryStatus",
                        "value": "ENABLED",
                        "op": "ne"
                    }
                ],
                "actions": [
                    {
                        "type": "set-continuous-backup"
                    }
                ]
            },
            session_factory=mock_factory,
        )
        try:
            p.resource_manager.actions[0].process([{'TableName': 'abc', 'TableStatus': 'ACTIVE'}])
        except client.exceptions.TableNotFoundException:
            self.fail('should not raise')
        mock_factory().client('dynamodb').update_continuous_backups.assert_called_once()

    def test_dynamodb_mark(self):
        session_factory = self.replay_flight_data("test_dynamodb_mark")
        client = session_factory().client("dynamodb")
        p = self.load_policy(
            {
                "name": "dynamodb-mark",
                "resource": "dynamodb-table",
                "filters": [
                    {"TableName": "c7n-test"},
                    {'tag:test_tag': 'absent'}
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "days": 1,
                        "op": "delete",
                        "tag": "test_tag",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        arn = resources[0]["TableArn"]
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_of_resource(ResourceArn=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["Tags"]}

        localtz = tzutil.gettz("America/New_York")
        dt = datetime.datetime.now(localtz)
        dt = dt.replace(year=2018, month=6, day=8, hour=7, minute=00)
        result = datetime.datetime.strptime(
            tag_map["test_tag"].strip().split("@", 1)[-1], "%Y/%m/%d"
        ).replace(
            tzinfo=localtz
        )
        self.assertEqual(result.date(), dt.date())

    def test_dynamodb_tag(self):
        session_factory = self.replay_flight_data("test_dynamodb_tag")
        client = session_factory().client("dynamodb")
        p = self.load_policy(
            {
                "name": "dynamodb-tag-table",
                "resource": "dynamodb-table",
                "filters": [{"TableName": "rolltop"}],
                "actions": [{"type": "tag", "tags": {"new_tag_key": "new_tag_value"}}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        arn = resources[0]["TableArn"]
        tags = client.list_tags_of_resource(ResourceArn=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["Tags"]}
        self.assertEqual(
            {"test_key": "test_value", "new_tag_key": "new_tag_value"}, tag_map
        )

    def test_dynamodb_unmark(self):
        session_factory = self.replay_flight_data("test_dynamodb_unmark")
        client = session_factory().client("dynamodb")
        p = self.load_policy(
            {
                "name": "dynamodb-unmark",
                "resource": "dynamodb-table",
                "filters": [{"TableName": "rolltop"}],
                "actions": [{"type": "remove-tag", "tags": ["test_key"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        arn = resources[0]["TableArn"]
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_of_resource(ResourceArn=arn)
        self.assertFalse("test_key" in tags)

    def test_dynamodb_create_backup(self):
        dt = datetime.datetime.now().replace(
            year=2018, month=1, day=16, hour=19, minute=39
        )
        suffix = dt.strftime("%Y-%m-%d-%H-%M")

        session_factory = self.replay_flight_data("test_dynamodb_create_backup")

        p = self.load_policy(
            {
                "name": "c7n-dynamodb-create-backup",
                "resource": "dynamodb-table",
                "filters": [{"TableName": "c7n-dynamodb-backup"}],
                "actions": [{"type": "backup"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("dynamodb")
        arn = resources[0]["c7n:BackupArn"]
        table = client.describe_backup(BackupArn=arn)
        self.assertEqual(
            table["BackupDescription"]["BackupDetails"]["BackupName"],
            "Backup-c7n-dynamodb-backup-%s" % (suffix),
        )

    def test_dynamodb_create_prefixed_backup(self):
        dt = datetime.datetime.now().replace(
            year=2018, month=1, day=22, hour=13, minute=42
        )
        suffix = dt.strftime("%Y-%m-%d-%H-%M")

        session_factory = self.replay_flight_data(
            "test_dynamodb_create_prefixed_backup"
        )

        p = self.load_policy(
            {
                "name": "c7n-dynamodb-create-prefixed-backup",
                "resource": "dynamodb-table",
                "filters": [{"TableName": "c7n-dynamodb-backup"}],
                "actions": [{"type": "backup", "prefix": "custom"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("dynamodb")
        arn = resources[0]["c7n:BackupArn"]
        table = client.describe_backup(BackupArn=arn)
        self.assertEqual(
            table["BackupDescription"]["BackupDetails"]["BackupName"],
            "custom-c7n-dynamodb-backup-%s" % (suffix),
        )

    def test_dynamodb_delete_backup(self):
        factory = self.replay_flight_data("test_dynamodb_delete_backup")
        p = self.load_policy(
            {
                "name": "c7n-dynamodb-delete-backup",
                "resource": "dynamodb-backup",
                "filters": [{"TableName": "omnissm-registrations"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_dynamodb_enable_stream(self):
        factory = self.replay_flight_data("test_dynamodb_enable_stream")
        p = self.load_policy(
            {
                "name": "c7n-dynamodb-enable-stream",
                "resource": "dynamodb-table",
                "filters": [{"TableName": "c7n-test"}, {"TableStatus": "ACTIVE"}],
                "actions": [
                    {
                        "type": "set-stream",
                        "state": True,
                        "stream_view_type": "NEW_IMAGE",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        stream_field = resources[0]["c7n:StreamState"]
        stream_type = resources[0]["c7n:StreamType"]

        self.assertEqual(len(resources), 1)
        self.assertTrue(stream_field)
        self.assertEqual("NEW_IMAGE", stream_type)

    def test_export_description_filter(self):
        session_factory = self.replay_flight_data("test_dynamodb_export_description_filter")
        p = self.load_policy(
            {
                "name": "dynamodb-exports-s3-owner",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "export-description",
                        "key": "S3BucketOwner",
                        "value": "408502716114"
                    },
                    {
                        "type": "export-description",
                        "key": "ExportStatus",
                        "op": "in",
                        "value": ["COMPLETED"]
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("c7n:ExportDescription" in resources[0])

        exports = resources[0]["c7n:ExportDescription"]
        self.assertEqual(len(exports), 1)
        self.assertEqual(exports[0]["S3BucketOwner"], "408502716114")


class DynamoDbAccelerator(BaseTest):

    def test_resources(self):
        session_factory = self.replay_flight_data("test_dax_resources")
        p = self.load_policy(
            {"name": "dax-resources", "resource": "dax"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Status"], "available")

    def test_dax_security_group(self):
        session_factory = self.replay_flight_data("test_dax_security_group_filter")
        p = self.load_policy(
            {
                "name": "dax-resources",
                "resource": "dax",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ClusterName"], "c7n-dax")

    def test_tagging(self):
        session_factory = self.replay_flight_data("test_dax_add_tags")
        p = self.load_policy(
            {
                "name": "dax-resources",
                "resource": "dax",
                "filters": [{"tag:Required": "absent"}],
                "actions": [{"type": "tag", "tags": {"Required": "Required"}}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ClusterName"], "c7n-dax")
        client = session_factory(region="us-east-1").client("dax")
        tags = client.list_tags(ResourceName=resources[0]["ClusterArn"])["Tags"]
        self.assertEqual(tags[0]["Value"], "Required")

    def test_remove_tagging(self):
        session_factory = self.replay_flight_data("test_dax_remove_tags")
        p = self.load_policy(
            {
                "name": "dax-resources",
                "resource": "dax",
                "filters": [{"tag:Required": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["Required"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ClusterName"], "c7n-dax")
        client = session_factory(region="us-east-1").client("dax")
        tags = client.list_tags(ResourceName=resources[0]["ClusterArn"])["Tags"]
        self.assertEqual(tags, [{"Key": "Name", "Value": "c7n-dax-test"}])

    def test_mark_for_op(self):
        session_factory = self.replay_flight_data("test_dax_mark_for_op")
        p = self.load_policy(
            {
                "name": "dax-resources",
                "resource": "dax",
                "filters": [
                    {"tag:custodian_cleanup": "absent"}, {"tag:Required": "absent"}
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 7,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ClusterName"], "c7n-dax")
        client = session_factory(region="us-east-1").client("dax")
        tags = client.list_tags(ResourceName=resources[0]["ClusterArn"])["Tags"]
        self.assertEqual(tags[0]["Key"], "custodian_cleanup")
        self.assertEqual(
            tags[0]["Value"], "Resource does not meet policy: delete@2018/05/15"
        )

    def test_delete(self):
        session_factory = self.replay_flight_data("test_dax_delete_cluster")
        p = self.load_policy(
            {
                "name": "dax-resources",
                "resource": "dax",
                "filters": [{"tag:Required": "absent"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('dax')
        clusters = client.describe_clusters()['Clusters']
        self.assertEqual(clusters[0]['Status'], 'deleting')

    def test_update_cluster(self):
        session_factory = self.replay_flight_data(
            'test_dax_update_cluster')
        p = self.load_policy({
            'name': 'dax-resources',
            'resource': 'dax',
            'filters': [{
                'ParameterGroup.ParameterGroupName': 'default.dax1.0'}],
            'actions': [{
                'type': 'update-cluster',
                'ParameterGroupName': 'testparamgroup'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterName'], 'c7n-dax')
        client = session_factory(region='us-east-1').client('dax')
        clusters = client.describe_clusters()['Clusters']
        self.assertEqual(clusters[0]['ParameterGroup']['ParameterGroupName'],
                         'testparamgroup')

    def test_modify_security_groups(self):
        session_factory = self.replay_flight_data(
            'test_dax_update_security_groups')
        p = self.load_policy({
            'name': 'dax-resources',
            'resource': 'dax',
            'filters': [{
                'type': 'security-group',
                'key': 'GroupName',
                'value': 'default'}],
            'actions': [{
                'type': 'modify-security-groups',
                'remove': 'matched',
                'add': 'sg-72916c3b'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterName'], 'c7n-dax')
        client = session_factory(region='us-east-1').client('dax')
        sgs = client.describe_clusters()['Clusters'][0]['SecurityGroups']
        self.assertDictEqual(sgs[0], {"Status": "adding",
                                      "SecurityGroupIdentifier": "sg-72916c3b"})
        self.assertDictEqual(sgs[1], {"Status": "removing",
                                      "SecurityGroupIdentifier": "sg-4b9ada34"})

    def test_subnet_group_filter(self):
        session_factory = self.replay_flight_data(
            "test_dax_subnet_group_filter")
        p = self.load_policy({
            "name": "dax-cluster",
            "resource": "dax",
            "filters": [{
                "type": "subnet",
                "key": "MapPublicIpOnLaunch",
                "value": False}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterName'], 'c7n-test')

    def test_dax_get_resource(self):
        session_factory = self.replay_flight_data('test_dax_get_resource')

        p = self.load_policy({
            'name': 'dax-cluster-gr', 'resource': 'dax'},
            session_factory=session_factory)
        resources = p.resource_manager.get_resources(
            ["c7n-test-cluster"])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['TotalNodes'], 1)

    def test_dynamodb_consecutive_backup_count_filter(self):
        session_factory = self.replay_flight_data("test_dynamodb_consecutive_backup_count_filter")
        p = self.load_policy(
            {
                "name": "dynamodb_consecutive_backup_count_filter",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "consecutive-backups",
                        "count": 2,
                        "period": "days",
                        "backuptype": "ALL",
                        "status": "AVAILABLE"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-08-31T00:00:00+00:00"), c7n.resources.dynamodb):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:DynamodbBackups'][0]['BackupStatus'], "AVAILABLE")
        self.assertEqual(resources[0]['c7n:DynamodbBackups'][0]['BackupType'], "USER")
        self.assertEqual(resources[0]['c7n:DynamodbBackups'][0]['BackupCreationDateTime'],
            datetime.datetime(2022, 8, 31, 19, 4, 52, 776000, tzinfo=datetime.timezone.utc))

    def test_dynamodb_consecutive_backup_hourly_count_filter(self):
        session_factory = self.replay_flight_data(
            "test_dynamodb_consecutive_backup_hourly_count_filter")
        p = self.load_policy(
            {
                "name": "dynamodb_consecutive_backup_count_filter",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "consecutive-backups",
                        "count": 2,
                        "period": "hours",
                        "backuptype": "ALL",
                        "status": "AVAILABLE"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-08-30T21:00:00+00:00"), c7n.resources.dynamodb):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_dynamodb_consecutive_backup_weekly_count_filter(self):
        session_factory = self.replay_flight_data(
            "test_dynamodb_consecutive_backup_weekly_count_filter")
        p = self.load_policy(
            {
                "name": "dynamodb_consecutive_backup_weekly_count_filter",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "consecutive-backups",
                        "count": 1,
                        "period": "weeks",
                        "backuptype": "ALL",
                        "status": "AVAILABLE"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-08-31T00:00:00+00:00"), c7n.resources.dynamodb):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_dynamodb_consecutive_aws_backup_count_filter(self):
        session_factory = self.replay_flight_data("test_dynamodb_consecutive_backup_count_filter")
        p = self.load_policy(
            {
                "name": "dynamodb_consecutive_aws_backup_count_filter",
                "resource": "dynamodb-table",
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
        with mock_datetime_now(parser.parse("2022-08-31T00:00:00+00:00"), c7n.filters.backup):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:AwsBackups'][0]['Status'], "COMPLETED")
        self.assertEqual(resources[0]['c7n:AwsBackups'][0]['CreationDate'],
            datetime.datetime(2022, 8, 31, 19, 4, 52, 776000, tzinfo=datetime.timezone.utc))

    def test_dynamodb_consecutive_aws_backup_hourly_count_filter(self):
        session_factory = self.replay_flight_data(
            "test_dynamodb_consecutive_backup_hourly_count_filter")
        p = self.load_policy(
            {
                "name": "dynamodb_consecutive_aws_backup_count_filter",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "consecutive-aws-backups",
                        "count": 2,
                        "period": "hours",
                        "status": "COMPLETED"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-08-30T21:00:00+00:00"), c7n.filters.backup):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_dynamodb_consecutive_aws_backup_weekly_count_filter(self):
        session_factory = self.replay_flight_data(
            "test_dynamodb_consecutive_backup_weekly_count_filter")
        p = self.load_policy(
            {
                "name": "dynamodb_consecutive_aws_backup_weekly_count_filter",
                "resource": "dynamodb-table",
                "filters": [
                    {
                        "type": "consecutive-aws-backups",
                        "count": 1,
                        "period": "weeks",
                        "status": "COMPLETED"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2022-08-31T00:00:00+00:00"), c7n.filters.backup):
            resources = p.run()
        self.assertEqual(len(resources), 1)
