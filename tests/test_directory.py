# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from .common import BaseTest, load_data
from c7n.resources.directory import CloudDirectoryQueryParser
from c7n.exceptions import PolicyValidationError


class CloudDirectoryTest(BaseTest):

    def test_cloud_directory(self):
        session_factory = self.replay_flight_data("test_cloud_directory")
        client = session_factory().client("clouddirectory")

        schema_arn = client.create_schema(Name="gooseberry").get("SchemaArn")
        self.addCleanup(client.delete_schema, SchemaArn=schema_arn)
        schema_data = load_data("sample-clouddir-schema.json")

        client.put_schema_from_json(
            SchemaArn=schema_arn, Document=json.dumps(schema_data)
        )

        published_schema = client.publish_schema(
            DevelopmentSchemaArn=schema_arn, Version="1"
        ).get(
            "PublishedSchemaArn"
        )
        self.addCleanup(client.delete_schema, SchemaArn=published_schema)

        dir_info = client.create_directory(Name="c7n-test", SchemaArn=published_schema)
        self.addCleanup(client.delete_directory, DirectoryArn=dir_info["DirectoryArn"])
        self.addCleanup(client.disable_directory, DirectoryArn=dir_info["DirectoryArn"])

        p = self.load_policy(
            {
                "name": "cloud-directory",
                "resource": "cloud-directory",
                "filters": [
                    {
                        "type": "value",
                        "key": "State",
                        "value": "DELETED",
                        "op": "not-equal",
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_cloud_directory_disable(self):
        factory = self.replay_flight_data("test_cloud_directory_disable")
        p = self.load_policy(
            {
                "name": "disable-cloud-directory",
                "resource": "cloud-directory",
                "filters": [{"Name": "test-cloud"}],
                "actions": [{"type": "disable"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted([r["Name"] for r in resources]),
            ["test-cloud"],
        )
        self.assertEqual(resources[0]["State"], "ENABLED")
        client = factory().client("clouddirectory")
        remainder = client.list_directories()["Directories"]
        self.assertEqual(len(remainder), 1)
        self.assertEqual(remainder[0]["State"], "DISABLED")

    def test_cloud_directory_delete(self):
        factory = self.replay_flight_data("test_cloud_directory_delete")
        p = self.load_policy(
            {
                "name": "delete-cloud-directory",
                "resource": "cloud-directory",
                "filters": [{"Name": "test-cloud"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted([r["Name"] for r in resources]),
            ["test-cloud"],
        )
        client = factory().client("clouddirectory")
        remainder = client.list_directories()["Directories"]
        self.assertEqual(len(remainder), 1)
        self.assertEqual(remainder[0]["State"], "DELETED")


class DirectoryTests(BaseTest):

    def test_directory_tag(self):
        session_factory = self.replay_flight_data("test_directory_tag")
        client = session_factory().client("ds")
        p = self.load_policy(
            {
                "name": "tag-directory",
                "resource": "directory",
                "filters": [{"tag:RequiredTag": "absent"}],
                "actions": [
                    {"type": "tag", "key": "RequiredId", "value": "RequiredValue"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["DirectoryId"], "d-90672a7419")
        tags = client.list_tags_for_resource(ResourceId="d-90672a7419")["Tags"]
        self.assertEqual(tags[0]["Key"], "RequiredId")
        self.assertEqual(tags[0]["Value"], "RequiredValue")

    def test_directory_remove_tag(self):
        session_factory = self.replay_flight_data("test_directory_remove_tag")
        client = session_factory().client("ds")
        p = self.load_policy(
            {
                "name": "tag-directory",
                "resource": "directory",
                "filters": [{"tag:RequiredId": "RequiredValue"}],
                "actions": [{"type": "remove-tag", "tags": ["RequiredId"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["DirectoryId"], "d-90672a7419")
        tags = client.list_tags_for_resource(ResourceId="d-90672a7419")["Tags"]
        self.assertEqual(len(tags), 0)

    def test_directory_delete(self):
        factory = self.replay_flight_data("test_directory_delete")
        p = self.load_policy(
            {
                "name": "delete-directory",
                "resource": "directory",
                "filters": [{"Name": "test.example.com"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted([r["Name"] for r in resources]),
            ["test.example.com"],
        )
        self.assertEqual(resources[0]["Stage"], "Creating")
        client = factory().client("ds")
        remainder = client.describe_directories()["DirectoryDescriptions"]
        self.assertEqual(len(remainder), 2)
        self.assertEqual(remainder[1]["Stage"], "Deleting")

    def test_directory_ldap_setting_no_settings(self):
        factory = self.replay_flight_data("test_directory_ldap_setting")
        p = self.load_policy(
            {
                "name": "ldap-disabled",
                "resource": "directory",
                "filters": [{"type": "ldap", "status": "Disabled"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_directory_ldap_setting_enabled(self):
        factory = self.replay_flight_data("test_directory_ldap_setting_enabled")
        p = self.load_policy(
            {
                "name": "ldap-enabled",
                "resource": "directory",
                "filters": [{"type": "ldap", "status": "Enabled"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:LDAPSSettings"][0]['LDAPSStatus'], "Enabled")

    def test_directory_settings(self):
        factory = self.replay_flight_data("test_directory_settings")
        p = self.load_policy(
            {
                "name": "tls_1_0-enabled",
                "resource": "directory",
                "filters": [{"type": "settings", "key": "TLS_1_0", "value": "Enable"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class CloudDirectoryQueryParse(BaseTest):

    def test_query(self):
        query_filters = [
            {'Name': 'tag:Name', 'Values': ['Test']},
            {'Name': 'state', 'Values': ['DISABLED']}]
        self.assertEqual(query_filters, CloudDirectoryQueryParser.parse(query_filters))

    def test_invalid_query(self):
        self.assertRaises(
            PolicyValidationError, CloudDirectoryQueryParser.parse, {})

        self.assertRaises(
            PolicyValidationError, CloudDirectoryQueryParser.parse, [None])

        self.assertRaises(
            PolicyValidationError, CloudDirectoryQueryParser.parse, [{'X': 1}])

        self.assertRaises(
            PolicyValidationError, CloudDirectoryQueryParser.parse, [
                {'name': 'state', 'Values': 'disabled'}])

        self.assertRaises(
            PolicyValidationError, CloudDirectoryQueryParser.parse, [
                {'name': 'state', 'Values': ['disabled']}])
