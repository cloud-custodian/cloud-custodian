# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data
import time


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

        self.assertEqual(
            p.resource_manager.get_urns([dataset]),
            ["gcp:bigquery::cloud-custodian:dataset/devxyz"],
        )

    def test_dataset_delete(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('bq-dataset-delete', project_id=project_id)
        p = self.load_policy(
            {
                'name': 'bq-dataset-delete',
                'resource': 'gcp.bq-dataset',
                'filters': [{'tag:delete_me': 'yes'}],
                'actions': [
                    'delete'
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        if self.recording:
            time.sleep(1)
        self.assertEqual(len(resources), 1)


class BigQueryJobTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('bq-job-query')
        p = self.load_policy({
            'name': 'bq-job-get',
            'resource': 'gcp.bq-job'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['status']['state'], 'DONE')
        self.assertEqual(resources[0]['jobReference']['location'], 'US')
        self.assertEqual(resources[0]['jobReference']['projectId'], 'cloud-custodian')

        # NOTE: confirm is a global resource
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            ["gcp:bigquery::cloud-custodian:job/US/bquxjob_4c28c9a7_16958c2791d"],
        )

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

        # NOTE: confirm is a global resource
        self.assertEqual(
            p.resource_manager.get_urns(job),
            ["gcp:bigquery::cloud-custodian:job/US/bquxjob_4c28c9a7_16958c2791d"],
        )


class BigQueryTableTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('bq-table-query')
        p = self.load_policy({
            'name': 'bq-table-query',
            'resource': 'gcp.bq-table'},
            session_factory=factory)
        resources = p.run()
        self.assertIn('tableReference', resources[0].keys())
        self.assertEqual('TABLE', resources[0]['type'])

        self.assertEqual(
            p.resource_manager.get_urns(resources),
            ["gcp:bigquery::cloud-custodian:table/test/test"],
        )

    def test_table_get(self):
        factory = self.replay_flight_data('bq-table-get')
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

        self.assertEqual(
            p.resource_manager.get_urns(job),
            ["gcp:bigquery::cloud-custodian:table/qqqqqqqqqqqqq/test"],
        )

    def test_table_delete(self):
        project_id = 'premise-governance-rd'
        factory = self.replay_flight_data('bq-table-delete', project_id=project_id)
        p = self.load_policy(
            {
                'name': 'bq-table-delete',
                'resource': 'gcp.bq-table',
                'filters': [{'tag:delete_me': 'yes'}],
                'actions': [
                    'delete'
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        if self.recording:
            time.sleep(1)
        self.assertEqual(len(resources), 1)
