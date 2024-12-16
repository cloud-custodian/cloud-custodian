# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from googleapiclient.errors import HttpError

from gcp_common import BaseTest, event_data

from pytest_terraform import terraform


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


class LoggingSinkBucketTest(BaseTest):

    def test_query(self):
        project_id = 'gcp-lab-custodian'
        bucket_name = 'for_test_12345678'
        factory = self.replay_flight_data('test-logging-sink-bucket-query', project_id)
        policy = self.load_policy({
            'name': 'logging-sink-bucket',
            'resource': 'gcp.logging-sink-bucket',
            'filters': [{
                'type': 'value',
                'key': 'locationType',
                'value': 'region'
            }]
        }, session_factory=factory)
        resources = policy.run()

        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]['name'], bucket_name)


class LoggingSinkTest(BaseTest):

    def test_query(self):
        project_id = 'cloud-custodian'
        sink_name = 'datasets_are_not_anon_or_pub_accessible'
        factory = self.replay_flight_data('test-logging-sink-query', project_id)
        policy = self.load_policy({
            'name': 'logging-sink',
            'resource': 'gcp.logging-sink',
            'filters': [{
                'type': 'value',
                'key': 'writerIdentity',
                'value': 'serviceAccount:cloud-logs@system.gserviceaccount.com'
            }]
        }, session_factory=factory)
        resources = policy.run()

        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]['name'], sink_name)


@terraform('logging_sink_bucket')
def test_retention_policies_log_bucket(test, logging_sink_bucket):
    session_factory = test.replay_flight_data('retention-policies-log-bucket')
    policy = test.load_policy({
        'name': 'logging-sink-bucket',
        'resource': 'gcp.logging-sink-bucket',
        'filters': [{'retentionPolicy.isLocked':
                    logging_sink_bucket['google_storage_bucket.c7n.retention_policy.is_locked']}]
    }, session_factory=session_factory)

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]['retentionPolicy']['isLocked'] is not True
