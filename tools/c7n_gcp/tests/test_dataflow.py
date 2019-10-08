# Copyright 2019 Capital One Services, LLC
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

from gcp_common import BaseTest, event_data


class DataflowJobTest(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('dataflow-job', project_id)
        p = self.load_policy({
            'name': 'dataflow-job',
            'resource': 'gcp.dataflow-job'},
            session_factory=factory)
        resource = p.run()
        self.assertEqual(len(resource), 1)
        self.assertEqual(resource[0]['name'], 'test')
        self.assertEqual(resource[0]['projectId'], project_id)
        self.assertEqual(resource[0]['location'], 'us-central1')

    def test_job_get(self):
        project_id = 'cloud-custodian'
        jod_id = "2019-05-16_04_24_18-6110555549864901093"
        factory = self.replay_flight_data(
            'dataflow-get-resource', project_id)
        p = self.load_policy({'name': 'job',
                              'resource': 'gcp.dataflow-job',
                              'mode': {
                                  'type': 'gcp-audit',
                                  'methods': ['storage.buckets.update']}
                              },
                             session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('df-job-create.json')
        resource = exec_mode.run(event, None)
        self.assertEqual(resource[0]['id'], jod_id)
        self.assertEqual(resource[0]['name'], 'test1')
        self.assertEqual(resource[0]['projectId'], project_id)
        self.assertEqual(resource[0]['location'], 'us-central1')
