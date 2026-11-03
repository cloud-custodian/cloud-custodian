# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
import time
from datetime import datetime, timedelta, timezone

import pytest
from pytest_terraform import terraform

from c7n.filters.core import FilterValidationError

# Leftover collections from an earlier recording run were trimmed from the
# flight data.

# Requests sent per read method while recording.
READS = {'search': 3, 'query': 2, 'batch_search': 1, 'aggregate': 4}
# What Cloud Monitoring reports: a batch search also counts as a search.
READ_COUNTS = {**READS, 'search': READS['search'] + READS['batch_search']}


def read_metric(read):
    return f'vectorsearch.googleapis.com/{read}/request_count'


@terraform('vector_search_collection', scope='session')
def test_vector_search_collection_query(test, vector_search_collection):
    factory = test.replay_flight_data('vector-search-collection-query')
    busy = vector_search_collection.outputs['busy_name']['value']
    idle = vector_search_collection.outputs['idle_name']['value']
    policy = test.load_policy(
        {'name': 'vector-search-collections', 'resource': 'gcp.vector-search-collection'},
        session_factory=factory,
    )
    # One call across all locations returns both.
    collections = sorted(policy.run(), key=lambda r: r['name'])
    assert [r['name'] for r in collections] == [busy, idle]
    assert collections[0]['labels']['env'] == 'c7n'
    assert policy.resource_manager.get_urns(collections) == [
        f'gcp:vectorsearch:us-central1:{test.project_id}:collection/c7n-active',
        f'gcp:vectorsearch:us-east1:{test.project_id}:collection/c7n-unused',
    ]


@terraform('vector_search_collection', scope='session')
def test_vector_search_collection_get(test, vector_search_collection):
    factory = test.replay_flight_data('vector-search-collection-get')
    busy = vector_search_collection.outputs['busy_name']['value']
    policy = test.load_policy(
        {'name': 'vector-search-collection-get', 'resource': 'gcp.vector-search-collection'},
        session_factory=factory,
    )
    collection = policy.resource_manager.get_resource({'resourceName': busy})
    assert collection['name'] == busy
    assert collection['displayName'] == 'c7n active collection'


def read_until_counted(project_id, collection, timeout=600, interval=15):
    """Send READS to a collection and wait until Cloud Monitoring counts them.

    Recording only. It uses its own session, so these calls aren't recorded.
    """
    import google.auth
    import requests
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform'])
    session = AuthorizedSession(credentials)
    search = {'vectorSearch': {'searchField': 'emb', 'vector': {'values': [1, 0, 0]}, 'topK': 1}}
    calls = {
        'search': ('search', search),
        'query': ('query', {'filter': {}}),
        'batch_search': ('batchSearch', {'searches': [search]}),
        'aggregate': ('aggregate', {'aggregate': 'COUNT'}),
    }
    for read, count in READS.items():
        method, body = calls[read]
        for _ in range(count):
            session.post(
                f'https://vectorsearch.googleapis.com/v1/{collection}/dataObjects:{method}',
                json=body, timeout=30,
            ).raise_for_status()

    collection_id = collection.rsplit('/', 1)[-1]
    start = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0)

    def counted(read):
        params = {
            'filter': (f'metric.type = "{read_metric(read)}" AND '
                       f'resource.labels.collection = "{collection_id}"'),
            'interval.startTime': start.isoformat(),
            'interval.endTime': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        try:
            resp = session.get(
                f'https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries',
                params=params, timeout=30)
        except (requests.ConnectionError, requests.Timeout):
            return 0
        if resp.status_code == 429 or resp.status_code >= 500:
            return 0
        resp.raise_for_status()
        return sum(
            int(point['value']['int64Value'])
            for series in resp.json().get('timeSeries', ())
            for point in series['points'])

    # Counts arrive in parts, so wait for the totals, not the first datapoint.
    deadline = time.time() + timeout
    for read, expected in READ_COUNTS.items():
        while counted(read) < expected:
            if time.time() >= deadline:
                raise TimeoutError(f'{read} for {collection_id} never reached {expected}')
            time.sleep(interval)


@terraform('vector_search_collection', scope='session')
def test_vector_search_collection_read_metrics(test, vector_search_collection):
    busy = vector_search_collection.outputs['busy_name']['value']
    idle = vector_search_collection.outputs['idle_name']['value']
    factory = test.replay_flight_data('vector-search-collection-metrics')
    if test.recording:
        read_until_counted(test.project_id, busy)

    def run(op, **extra):
        return test.load_policy(
            {
                'name': 'vector-search-collection-reads',
                'resource': 'gcp.vector-search-collection',
                'filters': [{
                    'type': 'metrics',
                    'name': read_metric(read),
                    'aligner': 'ALIGN_SUM',
                    'reducer': 'REDUCE_SUM',
                    'group-by-fields': ['resource.labels.collection'],
                    'days': 1,
                    'op': op,
                    'value': 0,
                    **extra,
                } for read in READS],
            },
            session_factory=factory,
        ).run()

    # The unused collection has no datapoints, so only missing-value matches
    # it. A broken metric key would match both.
    assert [r['name'] for r in run('lte', **{'missing-value': 0})] == [idle]

    active = run('gt')
    assert [r['name'] for r in active] == [busy]
    metrics = active[0]['c7n.metrics']
    counts = {
        read: int(metrics[f'{read_metric(read)}.ALIGN_SUM.REDUCE_SUM']
                  ['points'][0]['value']['int64Value'])
        for read in READS
    }
    assert counts == READ_COUNTS


@terraform('vector_search_collection', scope='session')
def test_vector_search_collection_index_filter(test, vector_search_collection):
    factory = test.replay_flight_data('vector-search-collection-index')
    busy = vector_search_collection.outputs['busy_name']['value']
    idle = vector_search_collection.outputs['idle_name']['value']

    def min_replicas(op, value):
        return {
            'type': 'index',
            'attrs': [{
                'type': 'value',
                'key': 'dedicatedInfrastructure.autoscalingSpec.minReplicaCount',
                'op': op,
                'value': value,
            }],
        }

    # One index listing per collection serves all three filters. The plain
    # filter goes first because a failed and/not block clears its annotations.
    policy = test.load_policy(
        {
            'name': 'vector-search-collection-index',
            'resource': 'gcp.vector-search-collection',
            'filters': [{'or': [
                {'type': 'index', 'count': 0},
                {'and': [min_replicas('gte', 1), {'not': [min_replicas('gte', 2)]}]},
            ]}],
        },
        session_factory=factory,
    )
    active, unused = sorted(policy.run(), key=lambda r: r['name'])
    assert (active['name'], unused['name']) == (busy, idle)
    assert [i['name'] for i in active['c7n:MatchedIndexes']] == [f'{busy}/indexes/c7n-idx']
    assert unused['c7n:Indexes'] == []

    # Check each filter alone, reusing the cached listings (no API calls).
    manager = policy.resource_manager

    def matches(data):
        index_filter = manager.filter_registry.factory(data, manager)
        return [r['name'] for r in index_filter.process(copy.deepcopy([active, unused]))]

    assert matches({'type': 'index'}) == [busy]
    assert matches({'type': 'index', 'count': 0}) == [idle]
    assert matches(min_replicas('gte', 1)) == [busy]
    assert matches(min_replicas('gte', 2)) == []


def test_vector_search_collection_metric_key_validation(test):
    with pytest.raises(FilterValidationError) as ectx:
        test.load_policy({
            'name': 'vector-search-collection-bad-key',
            'resource': 'gcp.vector-search-collection',
            'filters': [{
                'type': 'metrics',
                'name': 'vectorsearch.googleapis.com/index/replicas',
                # Index metrics carry an empty collection_id, so they can't
                # be matched to a collection.
                'metric-key': 'resource.labels.collection_id',
                'op': 'gt',
                'value': 0,
            }],
        })
    assert "supported keys: resource.labels.collection" in str(ectx.value)
