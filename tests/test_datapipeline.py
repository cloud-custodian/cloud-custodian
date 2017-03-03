# Copyright 2016 Capital One Services, LLC
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
from common import BaseTest


class DataPipelineTest(BaseTest):

    def test_reporting(self):
        factory = self.replay_flight_data('test_datapipeline_reporting')

        session = factory()
        client = session.client('datapipeline')
        pipeline = client.create_pipeline(
            name='PipelinesFTW', uniqueId='PipelinesFTW')
        pipe_id = pipeline['pipelineId']
        client.put_pipeline_definition(
            pipelineId=pipe_id,
            pipelineObjects=
                [{"id": "Default", "name": "Default", "fields": [
                    {"key": "workerGroup", "stringValue": "workerGroup"}]},
                 {"id": "Schedule", "name": "Schedule", "fields": [
                    {"key": "startDateTime",
                     "stringValue": "2012-12-12T00:00:00"},
                    {"key": "type", "stringValue": "Schedule"},
                    {"key": "period", "stringValue": "1 hour"},
                    {"key": "endDateTime",
                     "stringValue": "2012-12-21T18:00:00"}]},
                 {"id": "SayHello", "name": "SayHello", "fields": [
                    {"key": "type", "stringValue": "ShellCommandActivity"},
                    {"key": "command", "stringValue": "echo hello"},
                    {"key": "parent", "refValue": "Default"},
                    {"key": "schedule", "refValue": "Schedule"}]}
                  ])
        client.activate_pipeline(pipelineId=pipe_id)
        self.addCleanup(client.delete_pipeline, pipelineId=pipe_id)

        p = self.load_policy({
            'name': 'datapipeline-report',
            'resource': 'datapipeline',
            'filters': [
                {'name': 'PipelinesFTW'}],
            },
            config={'region': 'us-west-2'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'PipelinesFTW')
