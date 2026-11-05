# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Opt-in pytest fixtures for recording and replaying GCP audit events.

Import the fixtures and hook in conftest.py, or register this module as a
pytest plugin. Cloud clients are only constructed in recording mode.
"""

import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import time

import jmespath as jmespath_module
import pytest


PROJECT_ID = 'cloud-custodian'
_EMAIL = re.compile(r'[\w.+%-]+@[\w.-]+\.\w+')
_STAMP = re.compile(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(?:Z|\+00:00)')


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _timestamp(value):
    """Compare UTC timestamps without losing Cloud Logging nanoseconds."""
    match = _STAMP.fullmatch(value)
    if not match:
        raise ValueError('Expected a UTC ISO timestamp: {}'.format(value))
    return (datetime.datetime.fromisoformat(match[1]), (match[2] or '').ljust(9, '0'))


def _new_session():
    # Explicit credentials disable Session's global HTTP cache. Do not use
    # local_session(), which could reuse the policy flight-data transport.
    import google.auth
    from c7n_gcp.client import Session
    credentials, _ = google.auth.default()
    return Session(credentials=credentials)


class RecordedEvent:
    """Record LogEntries separately from policy API flight data.

    An integer ``after`` selects the operation following that zero-based
    index; -1 selects the first operation. Timestamp and event selectors
    select the first operation starting strictly after the given timestamp.
    """

    def __init__(self, directory, recording, start_time=None, session_factory=_new_session,
                 project_id=PROJECT_ID):
        self.directory = Path(directory)
        self.recording = recording
        self.start_time = start_time or _now()
        self.session_factory = session_factory
        self.project_id = project_id
        self._session = None
        self._results = {}

    def _sanitize(self, value, key=''):
        if isinstance(value, dict):
            return {k: self._sanitize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize(v, key) for v in value]
        if not isinstance(value, str):
            return value
        if key == 'callerIp':
            return '198.51.100.1'
        if value == self.project_id:
            value = PROJECT_ID
        value = re.sub(
            r'(?<=projects/){}(?=/|$)'.format(re.escape(self.project_id)),
            PROJECT_ID, value)
        return _EMAIL.sub('user@example.com', value)

    def __call__(self, resource_name, method, labels=None, jmespath=None, first=False,
                 timeout_seconds=120, poll_interval_seconds=5, after=None):
        if not isinstance(resource_name, str) or not resource_name:
            raise ValueError('resource_name must be a nonempty string')
        if not isinstance(method, str) or not method:
            raise ValueError('method must be a nonempty string')
        if timeout_seconds < 0 or poll_interval_seconds <= 0:
            raise ValueError(
                'timeout_seconds must be nonnegative and poll_interval_seconds positive')
        if not isinstance(first, bool):
            raise ValueError('first must be a boolean')
        if isinstance(after, bool) or (isinstance(after, int) and after < -1):
            raise ValueError('after index must be an integer >= -1')
        if after is not None and not isinstance(after, (int, str, dict)):
            raise ValueError('after must be an index, timestamp, or event dictionary')
        if isinstance(after, (str, dict)):
            _timestamp(after['timestamp'] if isinstance(after, dict) else after)
        expression = jmespath_module.compile(jmespath) if jmespath else None
        if self.recording and self._session is None:
            self._session = self.session_factory()
            self.project_id = self._session.get_default_project()
        query = self._sanitize({'resource_name': resource_name, 'method': method,
                                'labels': labels or {}})
        key = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()
        result_key = json.dumps([key, jmespath, first, self._sanitize(after)], sort_keys=True)
        if result_key in self._results:
            return copy.deepcopy(self._results[result_key])
        path = self.directory / '{}.json'.format(key)
        deadline = time.monotonic() + timeout_seconds
        collected = {}
        while True:
            if self.recording:
                for entry in self._get_entries(resource_name, method, labels or {}):
                    collected[json.dumps(entry, sort_keys=True)] = entry
                entries = list(collected.values())
            else:
                if not path.is_file():
                    raise FileNotFoundError('No recorded audit events at {}'.format(path))
                payload = json.loads(path.read_text())
                if payload.get('version') != 1 or payload.get('query') != query:
                    raise ValueError('Invalid audit recording at {}'.format(path))
                entries = payload['entries']
            selected = self._select(entries, expression, first, after)
            if selected is not None:
                if self.recording:
                    self.directory.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({
                        'version': 1, 'query': query, 'entries': self._sanitize(entries)
                    }, indent=2, sort_keys=True) + '\n')
                self._results[result_key] = copy.deepcopy(selected)
                return copy.deepcopy(selected)
            if not self.recording:
                raise LookupError('No matching complete operation in {}'.format(path))
            if time.monotonic() >= deadline:
                raise TimeoutError('No matching complete audit operation for {} ({})'.format(
                    resource_name, method))
            time.sleep(min(poll_interval_seconds, max(0, deadline - time.monotonic())))

    @staticmethod
    def _select(entries, expression, first, after):
        groups = {}
        seen = set()
        for entry in sorted(entries, key=lambda e: (
                _timestamp(e['timestamp']), e.get('insertId', ''), json.dumps(e, sort_keys=True))):
            digest = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            operation = entry.get('operation') or {}
            key = (operation.get('producer'), operation['id']) if operation.get('id') else digest
            groups.setdefault(key, []).append(entry)
        operations = sorted(groups.values(), key=lambda g: (
            _timestamp(g[0]['timestamp']), g[0].get('insertId', '')))
        # Filter whole operations, not individual entries, so a predicate that
        # matches the initial entry does not hide its completion entry.
        if expression:
            operations = [g for g in operations if any(expression.search(e) for e in g)]
        if isinstance(after, int):
            operations = operations[after + 1:after + 2]
        elif after is not None:
            stamp = _timestamp(after['timestamp'] if isinstance(after, dict) else after)
            operations = [g for g in operations if _timestamp(g[0]['timestamp']) > stamp][:1]
        if len(operations) > 1:
            raise ValueError('Multiple audit operations matched; narrow the filters or use after')
        if not operations:
            return None
        candidates = []
        for entry in operations[0]:
            op = entry.get('operation') or {}
            if op.get('first' if first else 'last') or not (op.get('first') or op.get('last')):
                candidates.append(entry)
        if candidates:
            return candidates[0] if first else candidates[-1]

    @staticmethod
    def _quote(value):
        return json.dumps(value)

    def _get_entries(self, resource_name, method, labels):
        filters = [
            'logName = {}'.format(self._quote(
                'projects/{}/logs/cloudaudit.googleapis.com%2Factivity'.format(self.project_id))),
            'protoPayload.resourceName : {}'.format(self._quote(resource_name)),
            'protoPayload.methodName : {}'.format(self._quote(method)),
            'timestamp >= {}'.format(self._quote(self.start_time.isoformat())),
        ]
        for key, value in sorted(labels.items()):
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                raise ValueError('Invalid resource label key: {}'.format(key))
            filters.append('resource.labels.{} = {}'.format(key, self._quote(value)))
        body = {'resourceNames': ['projects/{}'.format(self.project_id)],
                'filter': '\n'.join(filters), 'orderBy': 'timestamp asc'}
        client = self._session.client('logging', 'v2', 'entries')
        return [e for page in client.execute_paged_query('list', {'body': body})
                for e in page.get('entries', [])]


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    """Attach the pre-provisioning time and replay mode to Terraform results."""
    try:
        from pytest_terraform.tf import TerraformFixture
    except ImportError:
        yield
        return
    is_terraform = isinstance(fixturedef.func, TerraformFixture)
    started = _now() if is_terraform else None
    outcome = yield
    if is_terraform and outcome.excinfo is None:
        value = outcome.get_result()
        value._c7n_audit_setup = (started, fixturedef.func.replay)


@pytest.fixture
def event_log_recording_directory(request):
    """Override this fixture to choose the location of committed events."""
    name = re.sub(r'[^\w.-]', '_', request.node.name)
    return request.path.parent / 'data' / 'events' / name


@pytest.fixture
def recorded_event(request, test, event_log_recording_directory):
    started = _now()
    recorder = None

    def lookup(*args, **kwargs):
        nonlocal recorder
        if recorder is None:
            # Resolve lazily, when the test body calls us: all of the test's
            # Terraform fixtures (including wider scopes) have now run.
            setups = []
            for name in request.fixturenames:
                value = request.getfixturevalue(name)
                setup = getattr(value, '_c7n_audit_setup', None)
                if isinstance(setup, tuple) and len(setup) == 2:
                    setups.append(setup)
            if setups and len({replay for _, replay in setups}) != 1:
                raise ValueError('Terraform fixtures have conflicting recording/replay modes')
            recording = not setups[0][1] if setups else bool(getattr(test, 'recording', False))
            recorder = RecordedEvent(
                event_log_recording_directory, recording,
                min(s[0] for s in setups) if setups else started)
        return recorder(*args, **kwargs)

    return lookup
