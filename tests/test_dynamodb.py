# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest
import datetime
from dateutil import zoneinfo

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
        self.assertEqual(resources[0]["TableName"], "rolltop")
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
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["TableArn"]
        tags = client.list_tags_of_resource(ResourceArn=arn)
        tag_map = {t["Key"]: t["Value"] for t in tags["Tags"]}
        self.assertTrue("test_key" in tag_map)

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
                        "days": 0,
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

        localtz = zoneinfo.gettz("America/New_York")
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
