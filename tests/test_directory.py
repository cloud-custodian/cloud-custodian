# Copyright 2017 Capital One Services, LLC
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

import json

from .common import BaseTest, load_data


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
