# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json

import gcp_common
from gcp_common import audit_event_recorder


class FakeLoggingClient:

    def __init__(self, entries):
        self.entries = entries
        self.calls = []

    def execute_query(self, verb, arguments):
        self.calls.append((verb, arguments))
        return {'entries': self.entries}


class FakeSession:

    def __init__(self, client):
        self.logging_client = client

    def get_default_project(self):
        return 'test-project'

    def client(self, service, version, component):
        assert (service, version, component) == ('logging', 'v2', 'entries')
        return self.logging_client


def test_audit_event_recorder_writes_entries_and_duplicate_artifacts(
        tmp_path, monkeypatch):
    entries = [
        {'timestamp': '2025-01-01T00:00:01Z', 'insertId': 'b'},
        {'timestamp': '2025-01-01T00:00:00Z', 'insertId': 'a'},
    ]
    client = FakeLoggingClient(entries)
    session = FakeSession(client)

    monkeypatch.setattr(gcp_common, 'EVENT_DIR', str(tmp_path))

    recorder = audit_event_recorder(
        lambda: session,
        'foo.json',
        method='CreateKey',
        resource_name='projects/test-project/locations/global/keys/key-1',
        labels={
            'project_id': 'test-project',
        },
    )

    recorder.record()

    assert json.loads((tmp_path / 'foo.json').read_text()) == entries[1]
    assert json.loads((tmp_path / 'foo.json-1').read_text()) == entries[0]

    assert client.calls[0][0] == 'list'
    body = client.calls[0][1]['body']
    assert body['resourceNames'] == ['projects/test-project']
    assert body['orderBy'] == 'timestamp asc'
    assert (
        'logName = '
        '"projects/test-project/logs/cloudaudit.googleapis.com%2Factivity"'
        in body['filter']
    )
    assert 'protoPayload.methodName : "CreateKey"' in body['filter']
    assert (
        'protoPayload.resourceName : '
        '"projects/test-project/locations/global/keys/key-1"'
        in body['filter']
    )
    assert 'resource.labels.project_id = "test-project"' in body['filter']
    assert 'timestamp >= ' in body['filter']
