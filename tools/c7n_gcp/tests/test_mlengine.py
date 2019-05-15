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


class MLModelTest(BaseTest):

    def test_models_query(self):
        project_id = "cloud-custodian"

        session_factory = self.replay_flight_data(
            'ml-models-query', project_id)

        policy = self.load_policy(
            {
                'name': 'ml-models-query',
                'resource': 'gcp.ml-model'
            },
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_models_get(self):
        project_id = 'cloud-custodian'
        name = "test_model"

        session_factory = self.replay_flight_data(
            'ml-models-query-get', project_id)

        policy = self.load_policy(
            {
                'name': 'ml-models-query-get',
                'resource': 'gcp.ml-model'
            },
            session_factory=session_factory)

        resource = policy.resource_manager.get_resource({
            "name": name,
            "project_id": project_id,
        })

        self.assertEqual(resource['name'], "projects/cloud-custodian/models/{}".format(name))


class MLJobTest(BaseTest):

    def test_jobs_query(self):
        project_id = 'mythic-tribute-232915'  # 'cloud-custodian'

        session_factory = self.replay_flight_data(
            'ml-jobs-query', project_id)

        policy = self.load_policy(
            {
                'name': 'ml-jobs-query',
                'resource': 'gcp.ml-job'
            },
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_jobs_get(self):
        project_id = 'mythic-tribute-232915'  # 'cloud-custodian'
        id = "test_job"

        session_factory = self.replay_flight_data(
            'ml-jobs-query-get', project_id)

        policy = self.load_policy(
            {
                'name': 'ml-jobs-query-get',
                'resource': 'gcp.ml-job'
            },
            session_factory=session_factory)

        resource = policy.resource_manager.get_resource({
            "name": id,
            "project_id": project_id,
        })

        self.assertEqual(resource['jobId'], id)
