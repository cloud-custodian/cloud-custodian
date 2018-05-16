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

from .common import BaseTest, functional

# datapipeline is not available in us-east-2 where we run our functional tests
# so we do a forced override here.
REGION = "us-west-2"


class DataPipelineTest(BaseTest):

    def test_reporting(self):
        factory = self.replay_flight_data("test_datapipeline_reporting")

        session = factory()
        client = session.client("datapipeline")
        pipeline = client.create_pipeline(name="PipelinesFTW", uniqueId="PipelinesFTW")
        pipe_id = pipeline["pipelineId"]
        client.put_pipeline_definition(
            pipelineId=pipe_id,
            pipelineObjects=[
                {
                    "id": "Default",
                    "name": "Default",
                    "fields": [{"key": "workerGroup", "stringValue": "workerGroup"}],
                },
                {
                    "id": "Schedule",
                    "name": "Schedule",
                    "fields": [
                        {"key": "startDateTime", "stringValue": "2012-12-12T00:00:00"},
                        {"key": "type", "stringValue": "Schedule"},
                        {"key": "period", "stringValue": "1 hour"},
                        {"key": "endDateTime", "stringValue": "2012-12-21T18:00:00"},
                    ],
                },
                {
                    "id": "SayHello",
                    "name": "SayHello",
                    "fields": [
                        {"key": "type", "stringValue": "ShellCommandActivity"},
                        {"key": "command", "stringValue": "echo hello"},
                        {"key": "parent", "refValue": "Default"},
                        {"key": "schedule", "refValue": "Schedule"},
                    ],
                },
            ],
        )
        client.add_tags(pipelineId=pipe_id, tags=[{"key": "foo", "value": "bar"}])
        client.activate_pipeline(pipelineId=pipe_id)
        self.addCleanup(client.delete_pipeline, pipelineId=pipe_id)

        p = self.load_policy(
            {
                "name": "datapipeline-report",
                "resource": "datapipeline",
                "filters": [{"tag:foo": "bar"}],
            },
            config={"region": REGION},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        resource = resources[0]
        self.assertEqual(resource["name"], "PipelinesFTW")
        self.assertEqual(resource["Tags"], [{"Key": "foo", "Value": "bar"}])
        self.assertEqual(resource["lastActivationTime"], "2017-03-13T11:37:36")
        self.assertEqual(resource["creationTime"], "2017-03-13T11:37:34")
        self.assertEqual(resource["sphere"], "PIPELINE")
        self.assertEqual(resource["version"], "1")
        self.assertEqual(resource["id"], "df-0993359USAD6HT96D2W")
        self.assertEqual(resource["pipelineState"], "SCHEDULING")
        self.assertEqual(resource["accountId"], "644160558196")
        self.assertEqual(resource["userId"], "AIDAIXI7ULG2SDYI3RBNM")
        self.assertEqual(resource["firstActivationTime"], "2017-03-13T11:37:36")

    def test_delete_datapipeline(self):
        factory = self.replay_flight_data("test_datapipeline_delete")
        p = self.load_policy(
            {
                "name": "delete-datapipeline",
                "resource": "datapipeline",
                "filters": [{"name": "test-delete-pipeline"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["name"], "test-delete-pipeline")
        client = factory().client("datapipeline")
        removed = client.describe_pipelines(pipelineIds=[resources[0]["id"]])
        self.assertEqual(
            removed["pipelineDescriptionList"][0]["fields"][12]["stringValue"],
            "DELETING",
        )

    @functional
    def test_tag_datapipeline(self):
        factory = self.replay_flight_data("test_datapipeline_tag", region=REGION)

        session = factory()
        client = session.client("datapipeline")
        pipeline = client.create_pipeline(
            name="PipelineTagTest", uniqueId="PipelineTagTest1"
        )
        pipe_id = pipeline["pipelineId"]
        self.addCleanup(client.delete_pipeline, pipelineId=pipe_id)
        p = self.load_policy(
            {
                "name": "datapipeline-tag-test",
                "resource": "datapipeline",
                "filters": [{"name": "PipelineTagTest"}],
                "actions": [{"type": "tag", "key": "key1", "value": "value1"}],
            },
            session_factory=factory,
        )
        p.run()
        response = client.describe_pipelines(pipelineIds=[pipe_id])
        self.assertEqual(
            response["pipelineDescriptionList"][0]["tags"],
            [{"key": "key1", "value": "value1"}],
        )

    @functional
    def test_mark_datapipeline(self):
        factory = self.replay_flight_data("test_datapipeline_mark", region=REGION)

        session = factory()
        client = session.client("datapipeline")
        pipeline = client.create_pipeline(
            name="PipelineMarkTest", uniqueId="PipelineMarkTest1"
        )
        pipe_id = pipeline["pipelineId"]
        self.addCleanup(client.delete_pipeline, pipelineId=pipe_id)
        p = self.load_policy(
            {
                "name": "datapipeline-mark-test",
                "resource": "datapipeline",
                "filters": [{"name": "PipelineMarkTest"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_mark",
                        "op": "delete",
                        "msg": "marked for op with no date",
                        "days": 7,
                    }
                ],
            },
            session_factory=factory,
        )
        p.run()
        response = client.describe_pipelines(pipelineIds=[pipe_id])
        self.assertEqual(
            response["pipelineDescriptionList"][0]["tags"],
            [{"key": "custodian_mark", "value": "marked for op with no date"}],
        )

    @functional
    def test_remove_tag_datapipeline(self):
        factory = self.replay_flight_data("test_datapipeline_remove_tag", region=REGION)

        session = factory()
        client = session.client("datapipeline")
        pipeline = client.create_pipeline(
            name="PipelineRemoveTagTest", uniqueId="PipelineRemoveTagTest1"
        )
        pipe_id = pipeline["pipelineId"]

        self.addCleanup(client.delete_pipeline, pipelineId=pipe_id)

        client.add_tags(
            pipelineId=pipe_id,
            tags=[{"key": "tag_to_remove", "value": "value of tag to remove"}],
        )
        response1 = client.describe_pipelines(pipelineIds=[pipe_id])
        num_tags = len(response1["pipelineDescriptionList"][0]["tags"])

        p = self.load_policy(
            {
                "name": "datapipeline-remove-tag-test",
                "resource": "datapipeline",
                "filters": [{"name": "PipelineRemoveTagTest"}],
                "actions": [{"type": "remove-tag", "tags": ["tag_to_remove"]}],
            },
            session_factory=factory,
        )
        p.run()
        response2 = client.describe_pipelines(pipelineIds=[pipe_id])
        self.assertEqual(
            len(response2["pipelineDescriptionList"][0]["tags"]), num_tags - 1
        )

    @functional
    def test_marked_for_op_datapipeline(self):
        factory = self.replay_flight_data(
            "test_datapipeline_marked_for_op", region=REGION
        )

        session = factory()
        client = session.client("datapipeline")
        pipeline = client.create_pipeline(
            name="PipelineMarkedForOpTest", uniqueId="PipelineMarkedForOpTest1"
        )
        pipe_id = pipeline["pipelineId"]

        self.addCleanup(client.delete_pipeline, pipelineId=pipe_id)

        client.add_tags(
            pipelineId=pipe_id,
            tags=[
                {
                    "key": "pipeline_marked_for_op",
                    "value": "Pipeline marked for op: delete@2017-12-01",
                }
            ],
        )

        p = self.load_policy(
            {
                "name": "datapipeline-marked-for-op-test",
                "resource": "datapipeline",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "pipeline_marked_for_op",
                        "op": "delete",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
