# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest


class ReplInstance(BaseTest):

    def test_describe_augment_no_tags(self):
        session_factory = self.replay_flight_data(
            "test_dms_repl_instance_describe_sans_tags"
        )
        p = self.load_policy(
            {"name": "dms-replinstance", "resource": "dms-instance"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["ReplicationInstanceIdentifier"], "replication-instance-1"
        )

    def test_describe_get_resources(self):
        session_factory = self.replay_flight_data("test_dms_repl_instance_delete")
        p = self.load_policy(
            {"name": "dms-replinstance", "resource": "dms-instance"},
            session_factory=session_factory,
        )
        resources = p.resource_manager.get_resources(["replication-instance-1"])
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["ReplicationInstanceIdentifier"], "replication-instance-1"
        )

    def test_delete(self):
        session_factory = self.replay_flight_data("test_dms_repl_instance_delete")
        client = session_factory().client("dms")
        p = self.load_policy(
            {
                "name": "dms-replinstance",
                "resource": "dms-instance",
                "actions": ["delete"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["ReplicationInstanceIdentifier"], "replication-instance-1"
        )
        instances = client.describe_replication_instances().get("ReplicationInstances")
        self.assertEqual(instances[0]["ReplicationInstanceStatus"], "deleting")

    def test_modify(self):
        session_factory = self.replay_flight_data("test_dms_repl_instance_modify")
        client = session_factory().client("dms")
        p = self.load_policy(
            {
                "name": "dms-replinstance",
                "resource": "dms-instance",
                "filters": [
                    {"AutoMinorVersionUpgrade": False},
                    {"ReplicationInstanceClass": "dms.t2.small"},
                ],
                "actions": [
                    {
                        "type": "modify-instance",
                        "ApplyImmediately": True,
                        "AutoMinorVersionUpgrade": True,
                        "ReplicationInstanceClass": "dms.t2.medium",
                        "PreferredMaintenanceWindow": "Mon:23:00-Mon:23:59",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ReplicationInstanceIdentifier"], "rep-inst-1")
        ri = client.describe_replication_instances().get("ReplicationInstances")
        self.assertEqual(
            [
                ri[0]["AutoMinorVersionUpgrade"],
                ri[0]["PendingModifiedValues"]["ReplicationInstanceClass"],
                ri[0]["PreferredMaintenanceWindow"],
            ],
            [True, "dms.t2.medium", "mon:23:00-mon:23:59"],
        )


class ReplicationInstanceTagging(BaseTest):

    def test_replication_instance_tag(self):
        session_factory = self.replay_flight_data("test_dms_tag")
        p = self.load_policy(
            {
                "name": "tag-dms-instance",
                "resource": "dms-instance",
                "filters": [{"tag:RequiredTag": "absent"}],
                "actions": [
                    {"type": "tag", "key": "RequiredTag", "value": "RequiredValue"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("dms")
        tag_list = client.list_tags_for_resource(
            ResourceArn=resources[0]["ReplicationInstanceArn"]
        )[
            "TagList"
        ]
        tag_value = [t["Value"] for t in tag_list if t["Key"] == "RequiredTag"]
        self.assertEqual(tag_value[0], "RequiredValue")

    def test_remove_replication_instance_tag(self):
        session_factory = self.replay_flight_data("test_dms_tag_remove")
        p = self.load_policy(
            {
                "name": "remove-dms-tag",
                "resource": "dms-instance",
                "filters": [{"tag:RequiredTag": "RequiredValue"}],
                "actions": [{"type": "remove-tag", "tags": ["RequiredTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("dms")
        tag_list = client.list_tags_for_resource(
            ResourceArn=resources[0]["ReplicationInstanceArn"]
        )[
            "TagList"
        ]
        self.assertFalse([t for t in tag_list if t["Key"] == "RequiredTag"])

    def test_replication_instance_markforop(self):
        session_factory = self.replay_flight_data("test_dms_mark_for_op")
        p = self.load_policy(
            {
                "name": "dms-instance-markforop",
                "resource": "dms-instance",
                "filters": [{"tag:RequiredTag": "absent"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 2,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("dms")
        tag_list = client.list_tags_for_resource(
            ResourceArn=resources[0]["ReplicationInstanceArn"]
        )[
            "TagList"
        ]
        self.assertTrue(
            [t["Value"] for t in tag_list if t["Key"] == "custodian_cleanup"]
        )

    def test_replication_instance_markedforop(self):
        session_factory = self.replay_flight_data("test_dms_marked_for_op")
        p = self.load_policy(
            {
                "name": "dms-instance-markedforop",
                "resource": "dms-instance",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "skew": 2,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["ReplicationInstanceIdentifier"], "replication-instance-1"
        )


class DmsEndpointTests(BaseTest):

    def test_resource_query(self):
        session_factory = self.replay_flight_data("test_dms_resource_query")
        p = self.load_policy(
            {"name": "dms-endpoint-query", "resource": "dms-endpoint"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_endpoint_modify_sql(self):
        session_factory = self.replay_flight_data("test_dms_modify_endpoint_sql")
        p = self.load_policy(
            {
                "name": "dms-sql-ssl",
                "resource": "dms-endpoint",
                "filters": [
                    {"EndpointIdentifier": "c7n-dms-sql-ep"},
                    {"ServerName": "c7n-sql-db"},
                ],
                "actions": [
                    {
                        "type": "modify-endpoint",
                        "Port": 3305,
                        "SslMode": "require",
                        "Username": "admin",
                        "Password": "sqlpassword",
                        "ServerName": "c7n-sql-db-02",
                        "DatabaseName": "c7n-db-02",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("dms")
        ep = client.describe_endpoints()["Endpoints"][0]
        self.assertEqual(
            [
                ep["Port"],
                ep["SslMode"],
                ep["Username"],
                ep["ServerName"],
                ep["DatabaseName"],
            ],
            [3305, "require", "admin", "c7n-sql-db-02", "c7n-db-02"],
        )

    def test_endpoint_tag_filter(self):
        session_factory = self.replay_flight_data("test_dms_tag_filter")
        p = self.load_policy(
            {
                "name": "dms-sql-ssl",
                "resource": "dms-endpoint",
                "filters": [
                    {"tag:Owner": "pikachu"},
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Tags'], [{'Key': 'Owner', 'Value': 'pikachu'}])

    def test_dms_endpoint_delete(self):
        session_factory = self.replay_flight_data("test_dms_endpoint_delete")
        policy = {
            "name": "dms-delete-endpoint",
            "resource": "dms-endpoint",
            "filters": [{"EndpointIdentifier": "c7n-test"}],
            "actions": ["delete"],
        }
        policy = self.load_policy(policy, session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("dms")
        ep = client.describe_endpoints(
            Filters=[{"Name": "endpoint-id", "Values": ["c7n-test"]}]
        )[
            "Endpoints"
        ][
            0
        ]
        self.assertEqual(
            [ep["EndpointIdentifier"], ep["Status"]], ["c7n-test", "deleting"]
        )
