# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestQBusinessApplication(BaseTest):

    def test_application_query(self):
        factory = self.replay_flight_data("test_qbusiness_application")
        p = self.load_policy(
            {
                "name": "qbusiness-apps",
                "resource": "aws.qbusiness-application",
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["applicationArn"])
        self.assertIn("Tags", resources[0])

    def test_application_cross_account(self):
        factory = self.replay_flight_data("test_qbusiness_application_cross_account")
        p = self.load_policy(
            {
                "name": "qbusiness-app-cross-account",
                "resource": "aws.qbusiness-application",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["CrossAccountViolations"])

    def test_application_tag(self):
        factory = self.replay_flight_data("test_qbusiness_application_tag")
        client = factory().client("qbusiness")
        p = self.load_policy(
            {
                "name": "qbusiness-app-tag",
                "resource": "aws.qbusiness-application",
                "actions": [{"type": "tag", "key": "Env", "value": "Test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["applicationArn"]
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertEqual({t["key"]: t["value"] for t in tags}.get("Env"), "Test")

        p = self.load_policy(
            {
                "name": "qbusiness-app-untag",
                "resource": "aws.qbusiness-application",
                "filters": [{"tag:Env": "Test"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertNotIn("Env", [t["key"] for t in tags])


class TestQBusinessIndex(BaseTest):

    def test_index_query(self):
        factory = self.replay_flight_data("test_qbusiness_index")
        p = self.load_policy(
            {
                "name": "qbusiness-indices",
                "resource": "aws.qbusiness-index",
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["indexArn"])
        self.assertTrue(resources[0]["applicationId"])

    def test_index_tag(self):
        factory = self.replay_flight_data("test_qbusiness_index_tag")
        client = factory().client("qbusiness")
        p = self.load_policy(
            {
                "name": "qbusiness-index-tag",
                "resource": "aws.qbusiness-index",
                "actions": [{"type": "tag", "key": "Env", "value": "Test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["indexArn"]
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertEqual({t["key"]: t["value"] for t in tags}.get("Env"), "Test")

        p = self.load_policy(
            {
                "name": "qbusiness-index-untag",
                "resource": "aws.qbusiness-index",
                "filters": [{"tag:Env": "Test"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertNotIn("Env", [t["key"] for t in tags])


class TestQBusinessDataSource(BaseTest):

    def test_data_source_query(self):
        factory = self.replay_flight_data("test_qbusiness_data_source")
        p = self.load_policy(
            {
                "name": "qbusiness-data-sources",
                "resource": "aws.qbusiness-data-source",
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["dataSourceArn"])
        self.assertTrue(resources[0]["applicationId"])
        self.assertTrue(resources[0]["indexId"])

    def test_data_source_no_vpc(self):
        factory = self.replay_flight_data("test_qbusiness_data_source_no_vpc")
        p = self.load_policy(
            {
                "name": "qbusiness-data-source-no-vpc",
                "resource": "aws.qbusiness-data-source",
                "filters": [
                    {"type": "value",
                     "key": "vpcConfiguration",
                     "value": "absent"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_data_source_tag(self):
        factory = self.replay_flight_data("test_qbusiness_data_source_tag")
        client = factory().client("qbusiness")
        p = self.load_policy(
            {
                "name": "qbusiness-data-source-tag",
                "resource": "aws.qbusiness-data-source",
                "actions": [{"type": "tag", "key": "Env", "value": "Test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["dataSourceArn"]
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertEqual({t["key"]: t["value"] for t in tags}.get("Env"), "Test")

        p = self.load_policy(
            {
                "name": "qbusiness-data-source-untag",
                "resource": "aws.qbusiness-data-source",
                "filters": [{"tag:Env": "Test"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertNotIn("Env", [t["key"] for t in tags])


class TestQBusinessDataAccessor(BaseTest):

    def test_data_accessor_query(self):
        factory = self.replay_flight_data("test_qbusiness_data_accessor")
        p = self.load_policy(
            {
                "name": "qbusiness-data-accessors",
                "resource": "aws.qbusiness-data-accessor",
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["dataAccessorArn"])
        self.assertTrue(resources[0]["principal"])

    def test_data_accessor_tag(self):
        factory = self.replay_flight_data("test_qbusiness_data_accessor_tag")
        client = factory().client("qbusiness")
        p = self.load_policy(
            {
                "name": "qbusiness-data-accessor-tag",
                "resource": "aws.qbusiness-data-accessor",
                "actions": [{"type": "tag", "key": "Env", "value": "Test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["dataAccessorArn"]
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertEqual({t["key"]: t["value"] for t in tags}.get("Env"), "Test")

        p = self.load_policy(
            {
                "name": "qbusiness-data-accessor-untag",
                "resource": "aws.qbusiness-data-accessor",
                "filters": [{"tag:Env": "Test"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertNotIn("Env", [t["key"] for t in tags])


class TestQBusinessPlugin(BaseTest):

    def test_plugin_query(self):
        factory = self.replay_flight_data("test_qbusiness_plugin")
        p = self.load_policy(
            {
                "name": "qbusiness-plugins",
                "resource": "aws.qbusiness-plugin",
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["pluginArn"])

    def test_plugin_tag(self):
        factory = self.replay_flight_data("test_qbusiness_plugin_tag")
        client = factory().client("qbusiness")
        p = self.load_policy(
            {
                "name": "qbusiness-plugin-tag",
                "resource": "aws.qbusiness-plugin",
                "actions": [{"type": "tag", "key": "Env", "value": "Test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["pluginArn"]
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertEqual({t["key"]: t["value"] for t in tags}.get("Env"), "Test")

        p = self.load_policy(
            {
                "name": "qbusiness-plugin-untag",
                "resource": "aws.qbusiness-plugin",
                "filters": [{"tag:Env": "Test"}],
                "actions": [{"type": "remove-tag", "tags": ["Env"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(resourceARN=arn)["tags"]
        self.assertNotIn("Env", [t["key"] for t in tags])
