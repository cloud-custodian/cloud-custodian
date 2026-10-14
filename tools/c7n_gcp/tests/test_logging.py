# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from googleapiclient.errors import HttpError

from c7n.testing import C7N_FUNCTIONAL
from c7n_gcp.client import get_default_project
from gcp_common import BaseTest, event_data


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

    def test_sink_overlap_exact_filter(test):
        project_id = get_default_project()
        if C7N_FUNCTIONAL:
            session_factory = test.record_flight_data(
                'log-project-sink-overlap-exact', project_id=project_id)
        else:
            session_factory = test.replay_flight_data(
                'log-project-sink-overlap-exact', project_id=project_id)

        policy = test.load_policy(
            {
                'name': 'log-project-sink-overlap-exact',
                'resource': 'gcp.log-project-sink',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name',
                        'op': 'regex',
                        'value': '^c7n-sink-exact-',
                    },
                    {'type': 'sink-overlap', 'match': 'exact'},
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        names = {r['name'] for r in resources}

        assert 'c7n-sink-exact-a' in names
        assert 'c7n-sink-exact-b' in names
        assert 'c7n-sink-exact-no-filter-a' in names
        assert 'c7n-sink-exact-no-filter-b' in names
        assert 'c7n-sink-exact-non-match' not in names
        assert 'c7n-sink-exact-disabled' not in names

    def test_sink_overlap_overlap_filter(test):
        project_id = get_default_project()
        if C7N_FUNCTIONAL:
            session_factory = test.record_flight_data(
                'log-project-sink-overlap', project_id=project_id)
        else:
            session_factory = test.replay_flight_data(
                'log-project-sink-overlap', project_id=project_id)

        policy = test.load_policy(
            {
                'name': 'log-project-sink-overlap',
                'resource': 'gcp.log-project-sink',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name',
                        'op': 'regex',
                        'value': '^c7n-sink-overlap-',
                    },
                    {'type': 'sink-overlap'},
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        names = {r['name'] for r in resources}

        assert 'c7n-sink-overlap-base' in names
        assert 'c7n-sink-overlap-base-copy' in names
        assert 'c7n-sink-overlap-subset' in names
        # severity>=ERROR AND NOT resource.type="gce_instance" is a subset of base
        assert 'c7n-sink-overlap-exclusion' in names
        assert 'c7n-sink-overlap-non-match' not in names
        assert 'c7n-sink-overlap-disabled' not in names
        assert 'c7n-sink-overlap-other-destination' not in names

    def _process_sink_overlap(self, match, sinks):
        policy = self.load_policy({
            'name': 'log-project-sink-overlap-process',
            'resource': 'gcp.log-project-sink',
            'filters': [{'type': 'sink-overlap', 'match': match}]})
        matched = policy.resource_manager.filters[0].process(sinks)
        return {s['name']: s['c7n:matched-sinks'] for s in matched}

    def test_sink_overlap_annotates_direct_matches_only(self):
        destination = 'logging.googleapis.com/projects/p/locations/global/buckets/b'
        matched = self._process_sink_overlap('overlap', [
            {'name': 'low', 'destination': destination, 'filter': 'severity<=ERROR'},
            {'name': 'mid', 'destination': destination, 'filter': 'severity>=ERROR'},
            {'name': 'high', 'destination': destination, 'filter': 'severity>=CRITICAL'},
        ])
        # low and high only overlap through mid, so they are not peers.
        self.assertEqual(matched, {
            'low': ['mid'],
            'mid': ['low', 'high'],
            'high': ['mid'],
        })

    def test_sink_overlap_annotates_possible_matches_separately(self):
        destination = 'logging.googleapis.com/projects/p/locations/global/buckets/b'
        policy = self.load_policy({
            'name': 'log-project-sink-overlap-possible',
            'resource': 'gcp.log-project-sink',
            'filters': [{'type': 'sink-overlap'}]})
        matched = policy.resource_manager.filters[0].process([
            {'name': 'errors', 'destination': destination, 'filter': 'severity>=ERROR'},
            {'name': 'critical', 'destination': destination, 'filter': 'severity>=CRITICAL'},
            {'name': 'timeouts', 'destination': destination, 'filter': 'textPayload:"timeout"'},
            {'name': 'timeouts-copy', 'destination': destination,
             'filter': 'textPayload:"timeout"'},
            {'name': 'debug', 'destination': destination, 'filter': 'severity<=DEBUG'},
        ])
        annotations = {
            s['name']: (s['c7n:matched-sinks'], s['c7n:possible-matched-sinks'])
            for s in matched
        }
        self.assertEqual(annotations, {
            'errors': (['critical'], ['timeouts', 'timeouts-copy']),
            'critical': (['errors'], ['timeouts', 'timeouts-copy']),
            # Identical filters are proven duplicates even when unevaluable.
            'timeouts': (['timeouts-copy'], ['errors', 'critical', 'debug']),
            'timeouts-copy': (['timeouts'], ['errors', 'critical', 'debug']),
            'debug': ([], ['timeouts', 'timeouts-copy']),
        })

    def test_sink_overlap_unparseable_filters_do_not_fail_the_policy(self):
        destination = 'logging.googleapis.com/projects/p/locations/global/buckets/b'

        def sinks():
            return [
                {'name': 'base', 'destination': destination, 'filter': 'severity>=ERROR'},
                {'name': 'copy', 'destination': destination, 'filter': 'severity>=ERROR'},
                {'name': 'bad', 'destination': destination,
                 'filter': 'severity>=ERROR AND (resource.type="gce_instance"'},
                {'name': 'bad-copy', 'destination': destination,
                 'filter': 'severity>=ERROR  AND (resource.type="gce_instance"'},
                {'name': 'bad-exclusion', 'destination': destination,
                 'filter': 'severity>=ERROR',
                 'exclusions': [{'name': 'broken', 'filter': 'resource.type="gce_instance")'}]},
            ]

        with self.assertLogs('custodian.filters', level='WARNING') as logs:
            overlap = self._process_sink_overlap('overlap', sinks())
        self.assertEqual(len(logs.records), 3)
        self.assertIn('log sink bad:', logs.output[0])
        # Unparseable sinks are left out of overlap comparisons.
        self.assertEqual(overlap, {'base': ['copy'], 'copy': ['base']})

        with self.assertLogs('custodian.filters', level='WARNING'):
            exact = self._process_sink_overlap('exact', sinks())
        # Identical unparseable filters, ignoring whitespace, are duplicates.
        self.assertEqual(exact, {
            'base': ['copy'],
            'copy': ['base'],
            'bad': ['bad-copy'],
            'bad-copy': ['bad'],
        })

    def test_sink_overlap_applies_enabled_exclusions(self):
        destination = 'logging.googleapis.com/projects/p/locations/global/buckets/b'

        def sinks():
            return [
                {'name': 'base', 'destination': destination, 'filter': 'severity>=ERROR'},
                {'name': 'excluded', 'destination': destination, 'filter': 'severity>=ERROR',
                 'exclusions': [{'name': 'all', 'filter': 'severity>=ERROR'}]},
                {'name': 'disabled-exclusion', 'destination': destination,
                 'filter': 'severity>=ERROR',
                 'exclusions': [{'name': 'all', 'filter': 'severity>=ERROR',
                                 'disabled': True}]},
                {'name': 'partial-exclusion', 'destination': destination,
                 'filter': 'severity>=ERROR',
                 'exclusions': [{'name': 'gce', 'filter': 'resource.type="gce_instance"'}]},
            ]

        # An exclusion that removes every entry leaves nothing to overlap.
        self.assertEqual(self._process_sink_overlap('overlap', sinks()), {
            'base': ['disabled-exclusion', 'partial-exclusion'],
            'disabled-exclusion': ['base', 'partial-exclusion'],
            'partial-exclusion': ['base', 'disabled-exclusion'],
        })
        # Only sinks with the same filter and enabled exclusions are duplicates.
        self.assertEqual(self._process_sink_overlap('exact', sinks()), {
            'base': ['disabled-exclusion'],
            'disabled-exclusion': ['base'],
        })


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
