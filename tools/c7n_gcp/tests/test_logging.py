# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from googleapiclient.errors import HttpError

from gcp_common import BaseTest, event_data
from pytest_terraform import terraform


class LogProjectSinkTest(BaseTest):

    def test_query(self):
        project_id = self.project_id
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
                f'gcp:logging::{project_id}:project-sink/storage',
            ],
        )

    def test_get_project_sink(self):
        project_id = self.project_id
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
                f'gcp:logging::{project_id}:project-sink/testqqqqqqqqqqqqqqqqq',
            ],
        )

    def test_delete_project_sink(self):
        project_id = self.project_id
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
                # Whitespace inside a quoted string is significant.
                {'name': 'bad-spaced', 'destination': destination,
                 'filter': 'severity>=ERROR AND (resource.type="gce  instance"'},
                {'name': 'bad-spaced-copy', 'destination': destination,
                 'filter': 'severity>=ERROR AND (resource.type="gce instance"'},
                {'name': 'bad-exclusion', 'destination': destination,
                 'filter': 'severity>=ERROR',
                 'exclusions': [{'name': 'broken', 'filter': 'resource.type="gce_instance")'}]},
            ]

        with self.assertLogs('custodian.filters', level='WARNING') as logs:
            overlap = self._process_sink_overlap('overlap', sinks())
        self.assertEqual(len(logs.records), 5)
        self.assertIn('log sink bad:', logs.output[0])
        # Unparseable sinks are left out of overlap comparisons.
        self.assertEqual(overlap, {'base': ['copy'], 'copy': ['base']})

        with self.assertLogs('custodian.filters', level='WARNING'):
            exact = self._process_sink_overlap('exact', sinks())
        # Identical unparseable filters, ignoring whitespace outside quoted
        # strings, are duplicates.
        self.assertEqual(exact, {
            'base': ['copy'],
            'copy': ['base'],
            'bad': ['bad-copy'],
            'bad-copy': ['bad'],
        })

    def test_sink_overlap_ignores_comments(self):
        destination = 'logging.googleapis.com/projects/p/locations/global/buckets/b'

        def sinks():
            return [
                {'name': 'base', 'destination': destination, 'filter': 'severity>=ERROR'},
                {'name': 'commented', 'destination': destination,
                 'filter': 'severity>=ERROR -- was severity>=WARNING (see ticket'},
            ]

        # A commented filter used to produce a key that failed to re-parse.
        for match in ('overlap', 'exact'):
            self.assertEqual(self._process_sink_overlap(match, sinks()), {
                'base': ['commented'],
                'commented': ['base'],
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


@terraform('log_project_sink_exact')
def test_log_project_sink_exact(test, log_project_sink_exact):
    def name(resource):
        return log_project_sink_exact[f'google_logging_project_sink.{resource}.name']

    factory = test.replay_flight_data('log-project-sink-exact')
    policy = test.load_policy(
        {
            'name': 'log-project-sink-exact',
            'resource': 'gcp.log-project-sink',
            'filters': [
                {'type': 'value', 'key': 'name', 'op': 'regex', 'value': '^c7n-sink-exact-'},
                {'type': 'sink-overlap', 'match': 'exact'},
            ],
        },
        session_factory=factory,
    )
    resources = {r['name']: r for r in policy.run()}

    # Not matched: a different filter (non_match), disabled, an extra
    # exclusion (with_exclusion) and a different destination (other_destination).
    assert set(resources) == {name('a'), name('b'), name('no_filter_a'), name('no_filter_b')}
    assert resources[name('a')]['c7n:matched-sinks'] == [name('b')]
    assert resources[name('no_filter_a')]['c7n:matched-sinks'] == [name('no_filter_b')]


@terraform('log_project_sink_overlap')
def test_log_project_sink_overlap(test, log_project_sink_overlap):
    def name(resource):
        return log_project_sink_overlap[f'google_logging_project_sink.{resource}.name']

    factory = test.replay_flight_data('log-project-sink-overlap')
    policy = test.load_policy(
        {
            'name': 'log-project-sink-overlap',
            'resource': 'gcp.log-project-sink',
            'filters': [
                {'type': 'value', 'key': 'name', 'op': 'regex', 'value': '^c7n-sink-overlap-'},
                {'type': 'sink-overlap'},
            ],
        },
        session_factory=factory,
    )
    resources = {r['name']: r for r in policy.run()}

    # Not matched: severity<ERROR (non_match), disabled, an exclusion that
    # removes every entry (exclusion_all) and a different destination.
    overlapping = {
        name('base'),
        name('base_copy'),
        name('subset'),
        name('not_clause'),
        name('exclusion_partial'),
    }
    assert set(resources) == overlapping
    for sink_name, sink in resources.items():
        assert set(sink['c7n:matched-sinks']) == overlapping - {sink_name}
        assert sink['c7n:possible-matched-sinks'] == []


class LogProjectMetricTest(BaseTest):

    def test_query(self):
        project_id = self.project_id
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
                f'gcp:logging::{project_id}:project-metric/test',
            ],
        )

    def test_get_project_metric(self):
        project_id = self.project_id
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
                f'gcp:logging::{project_id}:project-metric/test_name',
            ],
        )


class LogExclusionTest(BaseTest):

    def test_query(self):
        project_id = self.project_id
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
                f'gcp:logging::{project_id}:exclusion/exclusions',
            ],
        )

    def test_get_project_exclusion(self):
        project_id = self.project_id
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
                f'gcp:logging::{project_id}:exclusion/qwerty',
            ],
        )
