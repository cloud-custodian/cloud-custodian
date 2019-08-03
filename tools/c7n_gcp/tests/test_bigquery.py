# Copyright 2018 Capital One Services, LLC
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


class BigQueryDataSetTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('bq-dataset-query')
        p = self.load_policy({
            'name': 'bq-get',
            'resource': 'gcp.bq-dataset'},
            session_factory=factory)
        dataset = p.resource_manager.get_resource(
            event_data('bq-dataset-create.json'))
        self.assertEqual(
            dataset['datasetReference']['datasetId'],
            'devxyz')
        self.assertTrue('access' in dataset)
        self.assertEqual(dataset['labels'], {'env': 'dev'})


class BigQueryJobTest(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('bq-job-query', project_id=project_id)
        p = self.load_policy({
            'name': 'bq-job-get',
            'resource': 'gcp.bq-job'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['status']['state'], 'DONE')
        self.assertEqual(resources[0]['jobReference']['location'], 'US')
        self.assertEqual(resources[0]['jobReference']['projectId'], project_id)

    def test_job_get(self):
        project_id = 'cloud-custodian'
        job_id = 'bquxjob_4c28c9a7_16958c2791d'
        location = 'US'
        factory = self.replay_flight_data('bq-job-get', project_id=project_id)
        p = self.load_policy({
            'name': 'bq-job-get',
            'resource': 'gcp.bq-job',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['google.cloud.bigquery.v2.JobService.InsertJob']
            }
        }, session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('bq-job-create.json')
        job = exec_mode.run(event, None)
        self.assertEqual(job[0]['jobReference']['jobId'], job_id)
        self.assertEqual(job[0]['jobReference']['location'], location)
        self.assertEqual(job[0]['jobReference']['projectId'], project_id)
        self.assertEqual(job[0]['id'], "{}:{}.{}".format(project_id, location, job_id))


class BigQueryProjectTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('bq-project-query')
        p = self.load_policy({
            'name': 'bq-get',
            'resource': 'gcp.bq-project'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['friendlyName'], 'test project')
        self.assertEqual(resources[0]['id'], 'cloud-custodian')


class BigQueryTableTest(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('bq-table-query', project_id=project_id)
        p = self.load_policy({
            'name': 'bq-table-query',
            'resource': 'gcp.bq-table'},
            session_factory=factory)
        resources = p.run()
        self.assertIn('tableReference', resources[0].keys())
        self.assertEqual('TABLE', resources[0]['type'])

    def test_table_get(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('bq-table-get', project_id=project_id)
        p = self.load_policy({
            'name': 'bq-table-get',
            'resource': 'gcp.bq-table',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['google.cloud.bigquery.v2.TableService.InsertTable']
            }
        }, session_factory=factory)
        exec_mode = p.get_execution_mode()
        event = event_data('bq-table-create.json')
        job = exec_mode.run(event, None)
        self.assertIn('tableReference', job[0].keys())
