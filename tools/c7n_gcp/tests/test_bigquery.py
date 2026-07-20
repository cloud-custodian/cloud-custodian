# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data
from c7n.exceptions import PolicyValidationError
from c7n_gcp.client import get_default_project
from c7n_gcp.filters.recommender import RecommenderFilter
from unittest.mock import patch
import time
from pytest_terraform import terraform


class BigQueryDataSetTest(BaseTest):
    def test_query(self):
        project_id = self.project_id
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
            [f"gcp:bigquery::{project_id}:dataset/devxyz"],
        )

    def test_dataset_delete(self):
        project_id = self.project_id
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

    def test_dataset_label(self):
        # Set the "env" label to not the default
        factory = self.replay_flight_data('bq-dataset-label')
        p = self.load_policy(
            {
                'name': 'bq-dataset-label',
                'resource': 'gcp.bq-dataset',
                'filters': [{
                    'type': 'value',
                    'key': 'id',
                    'op': 'contains',
                    'value': 'c7n_bq_dataset',
                }],
                'actions': [
                    {'type': 'set-labels',
                     'labels': {'env': 'not-the-default'}}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['labels']['env'], 'default')

        # Fetch the dataset manually to confirm the label was changed
        client = p.resource_manager.get_client()
        result = client.execute_query('get', resources[0]['datasetReference'])
        self.assertEqual(result['labels']['env'], 'not-the-default')


class BigQueryJobTest(BaseTest):
    def test_query(self):
        project_id = self.project_id
        factory = self.replay_flight_data('bq-job-query')
        p = self.load_policy({
            'name': 'bq-job-get',
            'resource': 'gcp.bq-job'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['status']['state'], 'DONE')
        self.assertEqual(resources[0]['jobReference']['location'], 'US')
        self.assertEqual(resources[0]['jobReference']['projectId'], project_id)

        # NOTE: confirm is a global resource
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [f"gcp:bigquery::{project_id}:job/US/bquxjob_4c28c9a7_16958c2791d"],
        )

    def test_job_get(self):
        project_id = self.project_id
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
            [f"gcp:bigquery::{project_id}:job/US/bquxjob_4c28c9a7_16958c2791d"],
        )


class BigQueryTableTest(BaseTest):
    def test_query(self):
        project_id = self.project_id
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
            [f"gcp:bigquery::{project_id}:table/test/test"],
        )

    def test_table_get(self):
        project_id = self.project_id
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
            [f"gcp:bigquery::{project_id}:table/qqqqqqqqqqqqq/test"],
        )

    def test_table_delete(self):
        project_id = self.project_id
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

    def test_table_label(self):
        # Set the "env" label to not the default
        factory = self.replay_flight_data('bq-table-label')
        p = self.load_policy(
            {
                'name': 'bq-table-label',
                'resource': 'gcp.bq-table',
                'filters': [{
                    'type': 'value',
                    'key': 'id',
                    'op': 'contains',
                    'value': 'c7n_bq_table',
                }],
                'actions': [
                    {'type': 'set-labels',
                     'labels': {'env': 'not-the-default'}}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['labels']['env'], 'default')

        # Fetch the table manually to confirm the label was changed
        client = p.resource_manager.get_client()
        result = client.execute_query('get', resources[0]['tableReference'])
        self.assertEqual(result['labels']['env'], 'not-the-default')


def test_dataset_update_validation_error(test):
    with test.assertRaisesRegex(
        PolicyValidationError,
        "policy:bq-dataset-update-invalid action:update "
        "requires at least one mutable dataset field"
    ):
        test.load_policy(
            {
                'name': 'bq-dataset-update-invalid',
                'resource': 'gcp.bq-dataset',
                'actions': [{'type': 'update'}]
            }
        )


@terraform("bigquery")
def test_dataset_update(test, bigquery):
    project_id = get_default_project()
    dataset_id = 'c7n_bq_dataset'

    session_factory = test.replay_flight_data(
        'bq-dataset-update', project_id=project_id)

    policy = test.load_policy(
        {
            'name': 'bq-dataset-update-access',
            'resource': 'gcp.bq-dataset',
            # Use BigQuery server-side dataset filter to avoid listing/augmenting
            # unrelated monitoring datasets in recordings.
            'query': [{'filter': 'labels.c7n_test_update:bq_dataset_update'}],
            'filters': [{
                'type': 'value',
                'key': 'datasetReference.datasetId',
                'value': dataset_id
            }],
            'actions': [{
                'type': 'update',
                'access': [
                    {'role': 'READER', 'specialGroup': 'projectReaders'},
                    {'role': 'WRITER', 'specialGroup': 'projectWriters'},
                    {'role': 'OWNER', 'specialGroup': 'projectOwners'}
                ]
            }]
        },
        session_factory=session_factory
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)

    client = policy.resource_manager.get_client()
    result = client.execute_query(
        'get',
        {'projectId': project_id, 'datasetId': dataset_id}
    )
    test.assertEqual(result['datasetReference']['datasetId'], dataset_id)
    expected_access = {
        ('READER', 'projectReaders'),
        ('WRITER', 'projectWriters'),
        ('OWNER', 'projectOwners'),
    }
    actual_access = {
        (entry.get('role'), entry.get('specialGroup'))
        for entry in result.get('access', [])
        if 'specialGroup' in entry
    }
    test.assertEqual(actual_access, expected_access)


@terraform("bigquery")
def test_table_recommend_partition_cluster_permissions(test, bigquery):
    project_id = get_default_project()
    session_factory = test.replay_flight_data(
        'bq-table-recommend-partition-cluster', project_id=project_id)

    # Baseline state prior to policy run:
    baseline_policy = test.load_policy(
        {
            'name': 'bq-table-recommend-partition-cluster-baseline',
            'resource': 'gcp.bq-table',
            # Restrict parent dataset enumeration to this test dataset label.
            'query': [{'filter': 'labels.c7n_test:bq_table_recommend_partition_cluster'}]
        },
        session_factory=session_factory,
    )
    baseline_resources = baseline_policy.run()
    test.assertEqual(len(baseline_resources), 1)
    test.assertEqual('c7n:recommend' in baseline_resources[0], False)
    policy = test.load_policy(
        {
            'name': 'bq-table-recommend-partition-cluster',
            'resource': 'gcp.bq-table',
            # Restrict parent dataset enumeration to this test dataset label.
            'query': [{'filter': 'labels.c7n_test:bq_table_recommend_partition_cluster'}],
            'filters': [{
                'type': 'recommend',
                'id': 'google.bigquery.table.PartitionClusterRecommender'
            }]
        },
        session_factory=session_factory,
    )
    test.assertEqual(policy.get_permissions(), {
        'bigquery.tables.list',
        'recommender.bigqueryPartitionClusterRecommendations.get',
        'recommender.bigqueryPartitionClusterRecommendations.list',
    })

    table_ref = baseline_resources[0]['tableReference']
    table_rid = (
        "//bigquery.googleapis.com/"
        f"projects/{table_ref['projectId']}/"
        f"datasets/{table_ref['datasetId']}/"
        f"tables/{table_ref['tableId']}"
    )
    # BigQuery partition/cluster recommendations are non deterministic from
    # workload history and may be absent during test runs; mock for deterministic
    # recommend-filter matching assertions.
    mocked_recommendations = [{
        'name': (
            f"projects/{table_ref['projectId']}/locations/global/recommenders/"
            "google.bigquery.table.PartitionClusterRecommender/recommendations/"
            "c7n-test-bq-table-recommendation"
        ),
        'recommenderSubtype': 'PARTITION_CLUSTER_TABLE',
        'content': {
            'operationGroups': [{
                'operations': [{'resource': table_rid}]
            }]
        }
    }]
    with patch.object(
        RecommenderFilter, 'get_recommendations', return_value=mocked_recommendations
    ):
        resources = policy.run()

    test.assertEqual(len(resources), 1)
    test.assertEqual('c7n:recommend' in resources[0], True)
    test.assertEqual(len(resources[0]['c7n:recommend']) >= 1, True)
    test.assertEqual(resources[0]['tableReference'], baseline_resources[0]['tableReference'])
    recommendation = resources[0]['c7n:recommend'][0]
    test.assertEqual(bool(recommendation['name']), True)
    test.assertEqual(bool(recommendation['recommenderSubtype']), True)
    test.assertEqual(
        'google.bigquery.table.PartitionClusterRecommender' in recommendation['name'],
        True
    )
