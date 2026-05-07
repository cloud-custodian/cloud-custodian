# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.testing import C7N_FUNCTIONAL
from c7n.exceptions import PolicyValidationError
from c7n_gcp.client import get_default_project
from googleapiclient.errors import HttpError
from pytest_terraform import terraform

from gcp_common import BaseTest, event_data


@terraform('log_bucket_get')
def test_log_bucket_get(test, log_bucket_get):
    log_bucket_name = (
        log_bucket_get.resources['google_logging_project_bucket_config']['test']['id']
    )

    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'log-bucket-get-resource', project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data('log-bucket-get-resource')

    policy = test.load_policy(
        {'name': 'log-bucket-get', 'resource': 'gcp.log-bucket'},
        session_factory=session_factory,
    )
    log_bucket_resource = policy.resource_manager.get_resource(
        {'resourceName': log_bucket_name}
    )
    test.assertEqual(log_bucket_resource['name'], log_bucket_name)


@terraform('log_bucket_filter_name')
def test_log_bucket_filter_name(test, log_bucket_filter_name):
    log_bucket_name = (
        log_bucket_filter_name.resources['google_logging_project_bucket_config']['test']['id']
    )

    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'log-bucket-filter-retention', project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data('log-bucket-filter-retention')

    policy = test.load_policy(
        {
            'name': 'log-bucket-filter-retention',
            'resource': 'gcp.log-bucket',
            'filters': [
                {'type': 'value', 'key': 'name', 'value': log_bucket_name}
            ],
        },
        session_factory=session_factory,
    )
    resources = policy.run()

    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]['name'], log_bucket_name)


@terraform('log_bucket_set_retention')
def test_log_bucket_set_retention(test, log_bucket_set_retention):
    log_bucket_name = (
        log_bucket_set_retention.resources['google_logging_project_bucket_config']['test']['id']
    )
    retention_days = (
        log_bucket_set_retention.resources['google_logging_project_bucket_config']['test']['retention_days']
    )

    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'log-bucket-set-retention', project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data('log-bucket-set-retention')

    policy = test.load_policy(
        {
            'name': 'log-bucket-set-retention',
            'resource': 'gcp.log-bucket',
            'filters': [{'type': 'value', 'key': 'name', 'value': log_bucket_name}],
            'actions': [{'type': 'set-retention', 'retentionDays': 7}],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]['name'], log_bucket_name)
    test.assertEqual(resources[0]['retentionDays'], retention_days)

    client = policy.resource_manager.get_client()
    updated = client.execute_query('get', {'name': log_bucket_name})
    test.assertEqual(updated['retentionDays'], 7)


def test_log_bucket_set_retention_requires_retention_days(test):
    with test.assertRaises(PolicyValidationError) as ctx:
        test.load_policy(
            {
                'name': 'log-bucket-set-retention-invalid',
                'resource': 'gcp.log-bucket',
                'actions': [{'type': 'set-retention'}],
            },
        )

    test.assertIn('retentionDays', str(ctx.exception))


class LogProjectSinkTest(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('log-project-sink-query', project_id)
        p = self.load_policy({
            'name': 'log-project-sink',
            'resource': 'gcp.log-project-sink'},
            session_factory=factory)
        resource = p.run()
        self.assertEqual(len(resource), 1)
        self.assertEqual(
            p.resource_manager.get_urns(resource),
            [
                'gcp:logging::cloud-custodian:project-sink/storage',
            ],
        )

    def test_get_project_sink(self):
        project_id = 'cloud-custodian'
        sink_name = "testqqqqqqqqqqqqqqqqq"
        factory = self.replay_flight_data(
            'log-project-sink-resource', project_id)
        p = self.load_policy({'name': 'log-project-sink-resource',
                              'resource': 'gcp.log-project-sink',
                              'mode': {
                                  'type': 'gcp-audit',
                                  'methods': ['google.logging.v2.ConfigServiceV2.CreateSink']}
                              },
                             session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('log-create-project-sink.json')
        resource = exec_mode.run(event, None)
        self.assertEqual(resource[0]['name'], sink_name)
        self.assertEqual(
            p.resource_manager.get_urns(resource),
            [
                'gcp:logging::cloud-custodian:project-sink/testqqqqqqqqqqqqqqqqq',
            ],
        )

    def test_delete_project_sink(self):
        project_id = 'custodian-tests'
        resource_name = "test-sink"
        factory = self.replay_flight_data(
            'log-project-sink-delete', project_id)
        policy = self.load_policy({'name': 'log-project-sink-delete',
                                   'resource': 'gcp.log-project-sink',
                                   'filters': [{'name': resource_name}],
                                   'actions': ['delete']},
                                  session_factory=factory)
        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)

        client = policy.resource_manager.get_client()
        sinkName = 'projects/{project_id}/sinks/{name}'.format(
            project_id=project_id,
            name=resource_name)

        with self.assertRaises(HttpError):
            client.execute_query('get', {'sinkName': sinkName})

    def test_bucket_filter(self):
        factory = self.replay_flight_data(
            'log-project-sink-bucket-filter',
            'cloud-custodian'
        )
        policy_data = {
            'name': 'log-project-sink-bucket-filter',
            'resource': 'gcp.log-project-sink',
            'filters': [
                {
                    'type': 'bucket',
                    'key': 'retentionPolicy.isLocked',
                    'op': 'ne',
                    'value': True
                }
            ]
        }

        policy = self.load_policy(policy_data, session_factory=factory)
        resources = policy.run()

        self.assertEqual(len(resources), 1)


class LogProjectMetricTest(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('log-project-metric-get', project_id)
        p = self.load_policy({
            'name': 'log-project-metric',
            'resource': 'gcp.log-project-metric'},
            session_factory=factory)
        resource = p.run()
        self.assertEqual(len(resource), 1)
        self.assertEqual(
            p.resource_manager.get_urns(resource),
            [
                'gcp:logging::cloud-custodian:project-metric/test',
            ],
        )

    def test_get_project_metric(self):
        project_id = 'cloud-custodian'
        metric_name = "test_name"
        factory = self.replay_flight_data(
            'log-project-metric-query', project_id)
        p = self.load_policy({'name': 'log-project-metric',
                              'resource': 'gcp.log-project-metric',
                              'mode': {
                                  'type': 'gcp-audit',
                                  'methods': ['google.logging.v2.MetricsServiceV2.CreateLogMetric']}
                              },
                             session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('log-create-project-metric.json')
        resource = exec_mode.run(event, None)
        self.assertEqual(resource[0]['name'], metric_name)
        self.assertEqual(
            p.resource_manager.get_urns(resource),
            [
                'gcp:logging::cloud-custodian:project-metric/test_name',
            ],
        )


class LogExclusionTest(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('log-exclusion', project_id)
        p = self.load_policy({
            'name': 'log-exclusion',
            'resource': 'gcp.log-exclusion'},
            session_factory=factory)
        resource = p.run()
        self.assertEqual(len(resource), 1)
        self.assertEqual(
            p.resource_manager.get_urns(resource),
            [
                'gcp:logging::cloud-custodian:exclusion/exclusions',
            ],
        )

    def test_get_project_exclusion(self):
        project_id = 'cloud-custodian'
        exclusion_name = "qwerty"
        factory = self.replay_flight_data(
            'log-exclusion-get', project_id)

        p = self.load_policy({'name': 'log-exclusion-get',
                              'resource': 'gcp.log-exclusion',
                              'mode': {
                                  'type': 'gcp-audit',
                                  'methods': ['google.logging.v2.ConfigServiceV2.CreateExclusion']}
                              },
                             session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('log-create-project-exclusion.json')
        resource = exec_mode.run(event, None)
        self.assertEqual(resource[0]['name'], exclusion_name)
        self.assertEqual(
            p.resource_manager.get_urns(resource),
            [
                'gcp:logging::cloud-custodian:exclusion/qwerty',
            ],
        )
