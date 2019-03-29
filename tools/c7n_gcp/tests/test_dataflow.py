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

from gcp_common import BaseTest


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
        jod_id = "2019-03-06_07_01_49-7812926814622315875"
        factory = self.replay_flight_data(
            'dataflow-get-resource', project_id)
        p = self.load_policy({'name': 'job', 'resource': 'gcp.dataflow-job'},
                             session_factory=factory)
        resource = p.resource_manager.get_resource({
            "project_id": project_id,
            "job_id": jod_id,
        })
        self.assertEqual(resource['id'], jod_id)
        self.assertEqual(resource['name'], 'test')
        self.assertEqual(resource['projectId'], project_id)
        self.assertEqual(resource['location'], 'us-central1')
