# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import copy
import datetime
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from c7n_gcp import testing
from pytest_terraform.tf import TerraformFixture, TerraformTestApi


@pytest.fixture
def event_log_recording_directory(tmp_path):
    return tmp_path


class ReplayTerraformFixture(TerraformFixture):
    """Exercise pytest registration and hooks without executing Terraform."""

    def __init__(self):
        self.tf_root_module = 'recorder_tf'
        self.replay = True

    def __call__(self):
        return TerraformTestApi({}, {})


recorder_tf = pytest.fixture(scope='module')(ReplayTerraformFixture())


def event(second=0, operation=None, **extra):
    entry = {'timestamp': '2026-01-01T00:00:{:02d}Z'.format(second),
             'insertId': str(second), **extra}
    if operation is not None:
        entry['operation'] = operation
    return entry


def pair(index=0, start=0):
    return [event(start, {'id': str(index), 'producer': 'service', 'first': True}),
            event(start + 1, {'id': str(index), 'producer': 'service', 'last': True})]


def recorder(tmp_path, batches):
    client = Mock()
    client.execute_paged_query.side_effect = [[{'entries': batch}] for batch in batches]
    session = Mock()
    session.get_default_project.return_value = 'live-project'
    session.client.return_value = client
    factory = Mock(return_value=session)
    return testing.RecordedEvent(tmp_path, True, session_factory=factory), client, factory


def test_pair_polls_until_complete_and_repeated_lookup_is_stable(tmp_path, monkeypatch):
    first, last = pair()
    record, client, factory = recorder(tmp_path, [[first], [first, last]])
    monkeypatch.setattr(testing.time, 'sleep', lambda delay: None)
    result = record('thing', 'create')
    assert result == last
    result['changed'] = True
    assert record('thing', 'create') == last
    assert client.execute_paged_query.call_count == 2
    factory.assert_called_once()


def test_first_record_and_replay_of_both_records(tmp_path):
    entries = pair()
    record, _, _ = recorder(tmp_path, [entries, entries])
    assert record('thing', 'create', first=True) == entries[0]
    assert record('thing', 'create') == entries[1]
    offline = testing.RecordedEvent(tmp_path, False, session_factory=Mock(
        side_effect=AssertionError('Replay must not create a cloud session')))
    assert offline('thing', 'create', first=True) == entries[0]
    assert offline('thing', 'create') == entries[1]


@pytest.mark.parametrize('operation', [None, {}, {'id': 'single'},
                                     {'id': 'single', 'first': True, 'last': True}])
def test_single_record_operation_supports_first_and_last(tmp_path, operation):
    entry = event(operation=operation)
    record, _, _ = recorder(tmp_path, [[entry], [entry]])
    assert record('thing', 'create') == entry
    assert record('thing', 'create', first=True) == entry


def test_multiple_operations_require_explicit_selection(tmp_path):
    entries = pair() + pair(1, 2)
    record, _, _ = recorder(tmp_path, [entries])
    with pytest.raises(ValueError, match='Multiple audit operations'):
        record('thing', 'create')


def test_after_indices_and_event_timestamp(tmp_path):
    entries = pair() + pair(1, 2) + pair(2, 4)
    record, _, _ = recorder(tmp_path, [list(reversed(entries))] * 5)
    first = record('thing', 'create', after=-1)
    assert first == entries[1]
    assert record('thing', 'create', after=0) == entries[3]
    assert record('thing', 'create', after=first) == entries[3]
    assert record('thing', 'create', after=entries[3]['timestamp']) == entries[5]


def test_duplicate_entries_do_not_create_ambiguity(tmp_path):
    entry = event()
    record, _, _ = recorder(tmp_path, [[entry, copy.deepcopy(entry)]])
    assert record('thing', 'create') == entry


def test_operation_producer_is_part_of_identity(tmp_path):
    entries = [event(operation={'id': 'same', 'producer': 'a'}),
               event(1, operation={'id': 'same', 'producer': 'b'})]
    record, _, _ = recorder(tmp_path, [entries])
    with pytest.raises(ValueError, match='Multiple'):
        record('thing', 'create')


def test_jmespath_filters_operations_without_losing_terminal_record(tmp_path):
    one = pair()
    one[0]['chosen'] = True
    entries = one + pair(1, 2)
    record, _, _ = recorder(tmp_path, [entries])
    assert record('thing', 'create', jmespath='chosen') == one[1]


def test_nanosecond_timestamps_are_ordered(tmp_path):
    a = event()
    b = event()
    a['timestamp'] = '2026-01-01T00:00:00.000000001Z'
    b['timestamp'] = '2026-01-01T00:00:00.000000002Z'
    record, _, _ = recorder(tmp_path, [[b, a], [b, a]])
    assert record('thing', 'create', after=-1) == a
    assert record('thing', 'create', after=a) == b


def test_pagination_and_structured_query(tmp_path):
    record, client, _ = recorder(tmp_path, [])
    client.execute_paged_query.side_effect = None
    client.execute_paged_query.return_value = [{'entries': pair()[:1]}, {'entries': pair()[1:]}]
    assert record('a"b', 'create', labels={'zone': 'us-central1-a'}) == pair()[1]
    body = client.execute_paged_query.call_args.args[1]['body']
    assert body['resourceNames'] == ['projects/live-project']
    assert 'protoPayload.resourceName : "a\\"b"' in body['filter']
    assert 'resource.labels.zone = "us-central1-a"' in body['filter']
    assert 'timestamp >=' in body['filter']


@pytest.mark.parametrize('entries', [[], pair()[:1]])
def test_timeout_reports_incomplete_or_missing_event(tmp_path, entries):
    record, _, _ = recorder(tmp_path, [entries])
    with pytest.raises(TimeoutError, match='No matching complete'):
        record('thing', 'create', timeout_seconds=0)
    assert not list(tmp_path.iterdir())


def test_replay_missing_event_fails_without_cloud_access(tmp_path):
    factory = Mock(side_effect=AssertionError('No network in replay'))
    replay = testing.RecordedEvent(tmp_path, False, session_factory=factory)
    with pytest.raises(FileNotFoundError):
        replay('thing', 'create')
    factory.assert_not_called()


def test_sanitized_recording_uses_same_key_with_replay_resource_name(tmp_path):
    entry = event(protoPayload={
        'resourceName': 'projects/live-project/things/t',
        'authenticationInfo': {'principalEmail': 'dev@example.org'},
        'authorizationInfo': [{'resource': 'projects/live-project'},
                              {'resource': 'projects/live-project/things/t'}],
        'requestMetadata': {'callerIp': '192.0.2.4'},
        'request': {'project': 'live-project', 'count': 2,
                    'image': 'projects/debian-cloud/images/i'},
    })
    record, _, _ = recorder(tmp_path, [[entry]])
    assert record('projects/live-project/things/t', 'create') == entry
    data = json.loads(next(tmp_path.iterdir()).read_text())
    assert 'live-project' not in json.dumps(data)
    replay = testing.RecordedEvent(tmp_path, False)
    payload = replay('projects/cloud-custodian/things/t', 'create')['protoPayload']
    assert payload['authenticationInfo']['principalEmail'] == 'user@example.com'
    assert payload['requestMetadata']['callerIp'] == '198.51.100.1'
    assert payload['request']['count'] == 2
    assert payload['request']['image'] == 'projects/debian-cloud/images/i'
    assert payload['authorizationInfo'] == [
        {'resource': 'projects/cloud-custodian'},
        {'resource': 'projects/cloud-custodian/things/t'},
    ]


@pytest.mark.parametrize('value, expected', [
    ('projects/live-project', 'projects/cloud-custodian'),
    ('projects/live-project/things/t', 'projects/cloud-custodian/things/t'),
    ('projects/live-project-other', 'projects/live-project-other'),
    ('projects/other-project', 'projects/other-project'),
])
def test_sanitize_project_resource_boundaries(tmp_path, value, expected):
    record = testing.RecordedEvent(tmp_path, True, project_id='live-project')
    assert record._sanitize(value) == expected


@pytest.mark.parametrize('kwargs', [
    {'after': -2}, {'after': True}, {'after': 1.5}, {'after': 'yesterday'},
    {'timeout_seconds': -1}, {'poll_interval_seconds': 0}, {'first': 'yes'},
])
def test_invalid_arguments_do_not_create_session(tmp_path, kwargs):
    record, _, factory = recorder(tmp_path, [])
    with pytest.raises(ValueError):
        record('thing', 'create', **kwargs)
    factory.assert_not_called()


def test_fixture_uses_earliest_terraform_time_and_replay_mode(monkeypatch, tmp_path):
    start = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    state = SimpleNamespace(_c7n_audit_setup=(start, True))
    request = SimpleNamespace(fixturenames=['tf'], getfixturevalue=lambda name: state)
    ctor = Mock()
    monkeypatch.setattr(testing, 'RecordedEvent', ctor)
    lookup = testing.recorded_event.__wrapped__(request, SimpleNamespace(recording=True), tmp_path)
    lookup('thing', 'create')
    ctor.assert_called_once_with(tmp_path, False, start)


def test_fixture_without_terraform_reads_test_recording_at_call_time(monkeypatch, tmp_path):
    request = SimpleNamespace(fixturenames=[])
    test = SimpleNamespace(recording=False)
    ctor = Mock()
    monkeypatch.setattr(testing, 'RecordedEvent', ctor)
    lookup = testing.recorded_event.__wrapped__(request, test, tmp_path)
    test.recording = True
    lookup('thing', 'create')
    assert ctor.call_args.args[1] is True


def test_fixture_rejects_mixed_terraform_modes(tmp_path):
    stamp = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    values = {str(i): SimpleNamespace(_c7n_audit_setup=(stamp, replay))
              for i, replay in enumerate((True, False))}
    request = SimpleNamespace(fixturenames=list(values), getfixturevalue=values.__getitem__)
    lookup = testing.recorded_event.__wrapped__(request, SimpleNamespace(), tmp_path)
    with pytest.raises(ValueError, match='conflicting'):
        lookup('thing', 'create')


def test_terraform_hook_captures_time_before_setup(monkeypatch):
    from pytest_terraform.tf import TerraformFixture
    fixture = object.__new__(TerraformFixture)
    fixture.replay = True
    stamp = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(testing, '_now', lambda: stamp)
    hook = testing.pytest_fixture_setup(SimpleNamespace(func=fixture), None)
    next(hook)
    state = SimpleNamespace()
    outcome = SimpleNamespace(excinfo=None, get_result=lambda: state)
    with pytest.raises(StopIteration):
        hook.send(outcome)
    assert state._c7n_audit_setup == (stamp, True)


def test_isolated_session_passes_explicit_credentials(monkeypatch):
    import google.auth
    import c7n_gcp.client
    credentials = object()
    monkeypatch.setattr(google.auth, 'default', lambda: (credentials, 'project'))
    session = Mock()
    monkeypatch.setattr(c7n_gcp.client, 'Session', session)
    assert testing._new_session() == session.return_value
    session.assert_called_once_with(credentials=credentials)


def test_registered_fixture_replays_without_terraform(
        recorded_event, event_log_recording_directory, test, monkeypatch):
    import google.auth
    monkeypatch.setattr(google.auth, 'default', Mock(side_effect=AssertionError('No cloud auth')))
    entry = event()
    record, _, _ = recorder(event_log_recording_directory, [[entry]])
    record('thing', 'create')
    test.recording = False
    assert recorded_event('thing', 'create') == entry


def test_registered_fixture_uses_scoped_terraform_replay(
        recorded_event, recorder_tf, event_log_recording_directory, test, monkeypatch):
    entry = event()
    record, _, _ = recorder(event_log_recording_directory, [[entry]])
    record('thing', 'create')
    test.recording = True  # Terraform mode has precedence over the test helper.
    constructor = Mock(wraps=testing.RecordedEvent)
    monkeypatch.setattr(testing, 'RecordedEvent', constructor)
    assert recorded_event('thing', 'create') == entry
    args = constructor.call_args.args
    assert args[1] is False
    assert args[2] == recorder_tf._c7n_audit_setup[0]


@pytest.mark.parametrize('first', [False, True])
def test_marked_operation_does_not_select_middle_entry(tmp_path, first):
    initial, terminal = pair()
    middle = event(1, {'id': '0', 'producer': 'service'})
    terminal['timestamp'] = '2026-01-01T00:00:02Z'
    entries = [middle, terminal] if first else [initial, middle]
    assert testing.RecordedEvent._select(entries, None, first, None) is None


def test_polling_waits_for_last_marker_after_middle_entry(tmp_path, monkeypatch):
    initial, terminal = pair()
    middle = event(1, {'id': '0', 'producer': 'service'})
    terminal['timestamp'] = '2026-01-01T00:00:02Z'
    record, client, _ = recorder(tmp_path, [[initial, middle], [terminal]])
    monkeypatch.setattr(testing.time, 'sleep', lambda delay: None)
    assert record('thing', 'create') == terminal
    assert client.execute_paged_query.call_count == 2


def test_predicates_use_sanitized_view_but_live_result_preserves_resource(tmp_path):
    entry = event(protoPayload={'resourceName': 'projects/live-project/things/t',
                               'authenticationInfo': {'principalEmail': 'dev@example.org'}})
    record, _, _ = recorder(tmp_path, [[entry]])
    predicate = "protoPayload.authenticationInfo.principalEmail == 'user@example.com'"
    live = record('projects/live-project/things/t', 'create', jmespath=predicate,
                  timeout_seconds=0)
    assert live == entry
    replay = testing.RecordedEvent(tmp_path, False)
    offline = replay('projects/cloud-custodian/things/t', 'create', jmespath=predicate)
    assert offline == record._sanitize(live)


def test_numeric_project_aliases_use_authoritative_metadata(tmp_path):
    entry = event(protoPayload={
        'projectId': 'live-project', 'projectNumber': 123456789012,
        'resourceName': 'projects/123456789012/things/t',
        'request': {'datasetId': 'live-project', 'otherDatasetId': '123456789012',
                    'publicImage': 'projects/987654321098/images/image'},
    })
    record, client, _ = recorder(tmp_path, [[entry]])
    client.execute_query.return_value = {'projectId': 'live-project',
                                        'projectNumber': '123456789012'}
    live = record('projects/123456789012/things/t', 'create')
    assert live == entry
    data = json.loads(next(tmp_path.iterdir()).read_text())
    payload = data['entries'][0]['protoPayload']
    assert payload['projectId'] == 'cloud-custodian'
    assert payload['projectNumber'] == 'cloud-custodian'
    assert payload['resourceName'] == 'projects/cloud-custodian/things/t'
    assert payload['request'] == entry['protoPayload']['request']
    client.execute_query.assert_called_once_with('get', {'projectId': 'live-project'})
    assert testing.RecordedEvent(tmp_path, False)(
        'projects/cloud-custodian/things/t', 'create') == record._sanitize(live)


def test_numeric_default_project_also_redacts_named_alias(tmp_path):
    entry = event(protoPayload={'resourceName': 'projects/live-project/things/t',
                               'projectNumber': '123456789012'})
    record, client, factory = recorder(tmp_path, [[entry]])
    factory.return_value.get_default_project.return_value = '123456789012'
    client.execute_query.return_value = {'projectId': 'live-project',
                                        'projectNumber': '123456789012'}
    record('projects/live-project/things/t', 'create')
    data = json.loads(next(tmp_path.iterdir()).read_text())
    assert data['query']['resource_name'] == 'projects/cloud-custodian/things/t'
    assert data['entries'][0]['protoPayload']['projectNumber'] == 'cloud-custodian'


def test_unrelated_numeric_project_is_preserved(tmp_path):
    record, client, _ = recorder(tmp_path, [[event(resource='projects/987654321098')]])
    client.execute_query.return_value = {'projectId': 'live-project',
                                        'projectNumber': '123456789012'}
    record('thing', 'create')
    data = json.loads(next(tmp_path.iterdir()).read_text())
    assert data['entries'][0]['resource'] == 'projects/987654321098'


@pytest.mark.parametrize('metadata', [
    {'projectId': 'another-project', 'projectNumber': '123456789012'},
    {'projectId': 'live-project'},
])
def test_invalid_project_metadata_does_not_write_recording(tmp_path, metadata):
    record, client, _ = recorder(tmp_path, [[event(resource='projects/123456789012')]])
    client.execute_query.return_value = metadata
    with pytest.raises(ValueError, match='recording project identity'):
        record('thing', 'create')
    assert not list(tmp_path.iterdir())


def test_project_metadata_access_failure_does_not_write_recording(tmp_path):
    record, client, _ = recorder(tmp_path, [[event(resource='projects/123456789012')]])
    client.execute_query.side_effect = PermissionError('Project metadata access denied')
    with pytest.raises(PermissionError, match='metadata access denied'):
        record('thing', 'create')
    assert not list(tmp_path.iterdir())


def test_named_project_recording_does_not_fetch_metadata(tmp_path):
    record, client, _ = recorder(tmp_path, [[event(resource='projects/live-project')]])
    record('thing', 'create')
    client.execute_query.assert_not_called()
