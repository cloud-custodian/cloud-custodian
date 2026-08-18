# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json

import gcp_common
from gcp_common import audit_event_recorder


class FakeLoggingClient:
    """Returns one queued batch of entries per execute_query call."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = []

    def execute_query(self, verb, arguments):
        self.calls.append((verb, arguments))
        entries = self.batches.pop(0) if self.batches else []
        return {'entries': entries}


class FakeSession:

    def __init__(self, client):
        self.logging_client = client

    def get_default_project(self):
        return 'test-project'

    def client(self, service, version, component):
        assert (service, version, component) == ('logging', 'v2', 'entries')
        return self.logging_client


def make_recorder(tmp_path, monkeypatch, batches, event_file='foo.json', **kw):
    monkeypatch.setattr(gcp_common, 'EVENT_DIR', str(tmp_path))
    client = FakeLoggingClient(batches)
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
    op1_last = {
        'insertId': 'c',
        'timestamp': '2025-01-01T00:00:02Z',
        'operation': {'id': 'op-1', 'last': True},
    }
    recorder, client = make_recorder(
        tmp_path, monkeypatch, [[op0_first, op1_first, op1_last]])

    recorder.record()

    assert read(tmp_path, 'foo-first.json') == op0_first
    assert read(tmp_path, 'foo-1-first.json') == op1_first
    assert read(tmp_path, 'foo-1-last.json') == op1_last


def test_collision_appends_index_after_extension(tmp_path, monkeypatch):
    (tmp_path / 'foo.json').write_text('{"pre-existing": true}')
    entry = {'insertId': 'a', 'timestamp': '2025-01-01T00:00:00Z'}
    recorder, client = make_recorder(tmp_path, monkeypatch, [[entry]])

    recorder.record()

    assert read(tmp_path, 'foo.json') == {'pre-existing': True}
    assert read(tmp_path, 'foo.json-1') == entry
