# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json

import gcp_common
from gcp_common import audit_event_recorder


class FakeLoggingClient:
    """Yields one queued batch of entries, in pages, per query call."""

    def __init__(self, batches, page_size=None):
        self.batches = list(batches)
        self.page_size = page_size
        self.calls = []

    def execute_paged_query(self, verb, arguments):
        self.calls.append((verb, arguments))
        entries = self.batches.pop(0) if self.batches else []
        size = self.page_size or len(entries) or 1
        for start in range(0, len(entries), size):
            yield {'entries': entries[start:start + size]}


class FakeSession:

    def __init__(self, client):
        self.logging_client = client

    def get_default_project(self):
        return 'test-project'

    def client(self, service, version, component):
        assert (service, version, component) == ('logging', 'v2', 'entries')
        return self.logging_client


def make_recorder(
        tmp_path, monkeypatch, batches, event_file='foo.json',
        page_size=None, **kw):
    monkeypatch.setattr(gcp_common, 'EVENT_DIR', str(tmp_path))
    client = FakeLoggingClient(batches, page_size)
    session = FakeSession(client)
    kw.setdefault('poll_interval', 0)
    recorder = audit_event_recorder(
        lambda: session, event_file, method='CreateThing', **kw)
    return recorder, client


def read(tmp_path, name):
    return json.loads((tmp_path / name).read_text())


def test_standalone_entry_written_and_stops_polling(tmp_path, monkeypatch):
    entry = {'insertId': 'a', 'timestamp': '2025-01-01T00:00:00Z'}
    recorder, client = make_recorder(tmp_path, monkeypatch, [[entry]])

    recorder.record()

    assert read(tmp_path, 'foo.json') == entry
    assert len(client.calls) == 1


def test_first_then_last_pair_writes_both_and_stops(tmp_path, monkeypatch):
    first = {
        'insertId': 'a',
        'timestamp': '2025-01-01T00:00:00Z',
        'operation': {'id': 'op-1', 'first': True},
    }
    last = {
        'insertId': 'b',
        'timestamp': '2025-01-01T00:00:01Z',
        'operation': {'id': 'op-1', 'last': True},
    }
    recorder, client = make_recorder(
        tmp_path, monkeypatch, [[first], [first, last]])

    recorder.record()

    assert read(tmp_path, 'foo-first.json') == first
    assert read(tmp_path, 'foo-last.json') == last
    assert len(client.calls) == 2


def test_dedup_entries_filters_seen_and_updates_seen(tmp_path, monkeypatch):
    recorder, client = make_recorder(tmp_path, monkeypatch, [])
    seen = set()
    entry_a = {'insertId': 'a'}
    entry_b = {'insertId': 'b'}

    first_pass = recorder._dedup_entries(seen, [entry_a, entry_b])
    second_pass = recorder._dedup_entries(seen, [entry_a, entry_b])

    assert first_pass == [entry_a, entry_b]
    assert second_pass == []


def test_repolling_the_same_entry_is_not_a_collision(tmp_path, monkeypatch):
    first = {
        'insertId': 'a',
        'timestamp': '2025-01-01T00:00:00Z',
        'operation': {'id': 'op-1', 'first': True},
    }
    last = {
        'insertId': 'b',
        'timestamp': '2025-01-01T00:00:01Z',
        'operation': {'id': 'op-1', 'last': True},
    }
    # Cloud Logging queries are cumulative from a fixed start time, so a
    # later poll re-returns entries an earlier poll already wrote.
    recorder, client = make_recorder(
        tmp_path, monkeypatch, [[first], [first], [first, last]])

    recorder.record()

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        'foo-first.json', 'foo-last.json']


def test_query_body_reflects_structured_filters(tmp_path, monkeypatch):
    entry = {'insertId': 'a', 'timestamp': '2025-01-01T00:00:00Z'}
    recorder, client = make_recorder(
        tmp_path, monkeypatch, [[entry]],
        resource_name='projects/test-project/things/thing-1',
        labels={'database_id': 'db-1'},
    )

    recorder.record()

    verb, arguments = client.calls[0]
    assert verb == 'list'
    body = arguments['body']
    assert body['resourceNames'] == ['projects/test-project']
    assert body['orderBy'] == 'timestamp asc'
    assert 'protoPayload.methodName : "CreateThing"' in body['filter']
    assert (
        'protoPayload.resourceName : '
        '"projects/test-project/things/thing-1"'
        in body['filter']
    )
    assert 'resource.labels.database_id = "db-1"' in body['filter']
    assert 'timestamp >= "' in body['filter']


def test_record_raises_after_timeout_with_no_matches(tmp_path, monkeypatch):
    recorder, client = make_recorder(
        tmp_path, monkeypatch, [], timeout=0)

    try:
        recorder.record()
    except AssertionError:
        pass
    else:
        raise AssertionError('expected record() to raise')

    assert not list(tmp_path.iterdir())


def test_second_distinct_operation_gets_index_suffix(tmp_path, monkeypatch):
    op0_first = {
        'insertId': 'a',
        'timestamp': '2025-01-01T00:00:00Z',
        'operation': {'id': 'op-0', 'first': True},
    }
    op1_first = {
        'insertId': 'b',
        'timestamp': '2025-01-01T00:00:01Z',
        'operation': {'id': 'op-1', 'first': True},
    }
    op0_last = {
        'insertId': 'c',
        'timestamp': '2025-01-01T00:00:02Z',
        'operation': {'id': 'op-0', 'last': True},
    }
    op1_last = {
        'insertId': 'd',
        'timestamp': '2025-01-01T00:00:03Z',
        'operation': {'id': 'op-1', 'last': True},
    }
    recorder, client = make_recorder(
        tmp_path, monkeypatch, [[op0_first, op1_first, op0_last, op1_last]])

    recorder.record()

    assert read(tmp_path, 'foo-first.json') == op0_first
    assert read(tmp_path, 'foo-last.json') == op0_last
    assert read(tmp_path, 'foo-1-first.json') == op1_first
    assert read(tmp_path, 'foo-1-last.json') == op1_last


def test_collision_appends_index_after_extension(tmp_path, monkeypatch):
    (tmp_path / 'foo.json').write_text('{"pre-existing": true}')
    entry = {'insertId': 'a', 'timestamp': '2025-01-01T00:00:00Z'}
    recorder, client = make_recorder(tmp_path, monkeypatch, [[entry]])

    recorder.record()

    assert read(tmp_path, 'foo.json') == {'pre-existing': True}
    assert read(tmp_path, 'foo.json-1') == entry


def test_other_operation_completing_first_does_not_stop_polling_early(
        tmp_path, monkeypatch):
    # A query filter without a narrow resource_name can match entries from
    # more than one operation. Polling must not stop as soon as ANY tracked
    # operation reaches its 'last' entry, or another operation matched by
    # the same filter is silently left incomplete.
    op0_first = {
        'insertId': 'a',
        'timestamp': '2025-01-01T00:00:00Z',
        'operation': {'id': 'op-0', 'first': True},
    }
    op1_first = {
        'insertId': 'b',
        'timestamp': '2025-01-01T00:00:01Z',
        'operation': {'id': 'op-1', 'first': True},
    }
    op1_last = {
        'insertId': 'c',
        'timestamp': '2025-01-01T00:00:02Z',
        'operation': {'id': 'op-1', 'last': True},
    }
    op0_last = {
        'insertId': 'd',
        'timestamp': '2025-01-01T00:00:03Z',
        'operation': {'id': 'op-0', 'last': True},
    }
    # op-1 completes entirely within the first poll; op-0's 'last' entry
    # only shows up on the second poll.
    recorder, client = make_recorder(
        tmp_path, monkeypatch,
        [[op0_first, op1_first, op1_last], [op0_last]])

    recorder.record()

    assert read(tmp_path, 'foo-first.json') == op0_first
    assert read(tmp_path, 'foo-last.json') == op0_last
    assert len(client.calls) == 2


def test_entries_are_collected_across_pages(tmp_path, monkeypatch):
    # entries.list defaults to 50 results per page, so a poll can span pages.
    entries = [
        {'insertId': str(i), 'timestamp': '2025-01-01T00:00:0{}Z'.format(i)}
        for i in range(3)
    ]
    recorder, client = make_recorder(
        tmp_path, monkeypatch, [entries], page_size=1)

    recorder.record()

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        'foo.json', 'foo.json-1', 'foo.json-2']


def test_record_raises_naming_the_incomplete_operation(tmp_path, monkeypatch):
    first = {
        'insertId': 'a',
        'timestamp': '2025-01-01T00:00:00Z',
        'operation': {'id': 'op-0', 'first': True},
    }
    recorder, client = make_recorder(
        tmp_path, monkeypatch, [[first]], timeout=0)

    try:
        recorder.record()
    except AssertionError as e:
        assert 'op-0' in str(e)
    else:
        raise AssertionError('expected record() to raise')


def test_sanitizes_project_email_and_caller_ip(tmp_path, monkeypatch):
    entry = {
        'insertId': 'a',
        'timestamp': '2025-01-01T00:00:00Z',
        'logName': 'projects/test-project/logs/cloudaudit.googleapis.com%2Factivity',
        'resource': {'labels': {'project_id': 'test-project'}},
        'protoPayload': {
            'authenticationInfo': {
                'principalEmail': 'dev@example.org',
                'principalSubject': 'user:dev@example.org',
                },
            'requestMetadata': {'callerIp': '71.33.198.228'},
            'resourceName': 'projects/test-project/zones/us-central1-a/disks/d',
            'response': {'user': 'dev@example.org'},
            },
        }
    recorder, client = make_recorder(tmp_path, monkeypatch, [[entry]])

    recorder.record()

    written = read(tmp_path, 'foo.json')
    payload = written['protoPayload']
    assert written['resource']['labels']['project_id'] == 'cloud-custodian'
    assert written['logName'].startswith('projects/cloud-custodian/logs/')
    assert payload['resourceName'] == (
        'projects/cloud-custodian/zones/us-central1-a/disks/d')
    assert payload['authenticationInfo'] == {
        'principalEmail': 'user@example.com',
        'principalSubject': 'user:user@example.com',
        }
    assert payload['response']['user'] == 'user@example.com'
    assert payload['requestMetadata']['callerIp'] == '198.51.100.1'


def test_sanitize_leaves_other_projects_and_non_strings(tmp_path, monkeypatch):
    entry = {
        'insertId': 'a',
        'timestamp': '2025-01-01T00:00:00Z',
        'protoPayload': {
            'request': {
                'sizeGb': 10,
                'sourceImage': 'projects/debian-cloud/global/images/family/debian-12',
                },
            },
        }
    recorder, client = make_recorder(tmp_path, monkeypatch, [[entry]])

    recorder.record()

    request = read(tmp_path, 'foo.json')['protoPayload']['request']
    assert request['sourceImage'] == (
        'projects/debian-cloud/global/images/family/debian-12')
    assert request['sizeGb'] == 10
