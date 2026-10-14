# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import functools
import hashlib
import json
import logging
import os
import re
import shutil
import time
import typing

from pathlib import Path

from c7n.schema import generate
from c7n.testing import (
    CustodianTestCore,
    TestUtils,
    reset_session_cache,
    C7N_FUNCTIONAL,
)

from c7n_gcp.client import Session, LOCAL_THREAD, get_default_project

from recorder import (
    HttpRecorder,
    HttpReplay,
    PROJECT_ID,
)


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'flights')
EVENT_DIR = os.path.join(os.path.dirname(__file__), 'data', 'events')


log = logging.getLogger('custodian.tests.gcp')

EMAIL_RE = re.compile(r'[\w.+%-]+@[\w.-]+\.\w+')
PLACEHOLDER_EMAIL = 'user@example.com'
# RFC 5737 TEST-NET-2, reserved for documentation.
PLACEHOLDER_IP = '198.51.100.1'


def event_data(fname):
    """Load a recorded audit LogEntry fixture.

    Fixtures name the placeholder project (see ``AuditEventRecorder``).
    When recording, put the live project back so the policy resolves its
    resource against an account that actually has one.
    """
    with open(os.path.join(EVENT_DIR, fname)) as fh:
        if C7N_FUNCTIONAL:
            return json.loads(fh.read().replace(PROJECT_ID, get_default_project()))
        return json.load(fh)


def audit_event_recorder(
        session_factory,
        event_file: str,
        method: str,
        resource_name: typing.Optional[str] = None,
        labels: typing.Optional[typing.Mapping[str, str]] = None,
        start_time_skew_seconds: int = 60,
        timeout: int = 120,
        poll_interval: int = 5,
) -> 'AuditEventRecorder':
    """Create a recorder for GCP audit LogEntry event fixtures.

    Construct it before triggering the API call, then call ``record()`` in
    recording mode. Matching log entries are written under ``data/events``.

    See ``docs/source/gcp/examples/audit-event-recording.rst`` for usage,
    filtering options, file naming, and caveats around multi-entry
    operations and creation events.
    """
    return AuditEventRecorder(
        session_factory,
        event_file,
        method,
        resource_name=resource_name,
        labels=labels,
        start_time_skew_seconds=start_time_skew_seconds,
        timeout=timeout,
        poll_interval=poll_interval,
    )


class AuditEventRecorder:

    def __init__(
            self,
            session_factory,
            event_file: str,
            method: str,
            resource_name: typing.Optional[str] = None,
            labels: typing.Optional[typing.Mapping[str, str]] = None,
            start_time_skew_seconds: int = 60,
            timeout: int = 120,
            poll_interval: int = 5,
    ) -> None:
        self.session_factory = session_factory
        self.event_file = event_file
        self.method = method
        self.resource_name = resource_name
        self.labels = labels or {}
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.start_time = (
            datetime.datetime.now(datetime.timezone.utc) -
            datetime.timedelta(seconds=start_time_skew_seconds)
        )

    def record(self) -> None:
        self.project_id = self.session_factory().get_default_project()
        deadline = time.time() + self.timeout
        operations: dict = {}
        seen_hashes: set = set()
        while True:
            entries = self._dedup_entries(seen_hashes, self._get_entries())
            if entries:
                self._write_batch(entries, operations)
                if all(s['complete'] for s in operations.values()):
                    return
            if time.time() >= deadline:
                incomplete = [
                    op_id for op_id, state in operations.items()
                    if not state['complete']
                ]
                if incomplete:
                    raise AssertionError(
                        'Timed out recording {}, waiting on operations: {}'
                        .format(self.event_file, ', '.join(incomplete)))
                raise AssertionError(
                    'No GCP audit log entries matched {}'.format(self.event_file))
            time.sleep(self.poll_interval)

    def _dedup_entries(self, seen: set, entries: list[dict]) -> list[dict]:
        """Update seen with each entry's hash. Return the entries not in seen.

        Cloud Logging queries are cumulative from a fixed start time, so a
        later poll re-returns entries an earlier poll already saw.
        """
        new_entries = []
        for entry in entries:
            digest = hashlib.sha256(
                json.dumps(entry, sort_keys=True).encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            new_entries.append(entry)
        return new_entries

    def _write_batch(self, entries: list[dict], operations: dict) -> None:
        """Write one poll batch, updating per-operation state.

        ``operations`` maps ``operation.id`` to its assigned file-name index
        and whether its ``last`` entry has been seen.
        """
        for entry in entries:
            payload = json.dumps(
                self._sanitize(entry), indent=2, sort_keys=True) + '\n'
            operation = entry.get('operation') or {}
            operation_id = operation.get('id')
            if not operation_id:
                self._write_entry(self.event_file, payload)
                continue
            state = operations.setdefault(
                operation_id, {'index': len(operations), 'complete': False})
            self._write_entry(
                self._operation_file_name(state['index'], operation), payload)
            if operation.get('last'):
                state['complete'] = True

    def _operation_file_name(self, index: int, operation: dict) -> str:
        base, ext = os.path.splitext(self.event_file)
        parts = [base]
        if index > 0:
            parts.append(str(index))
        if operation.get('first'):
            parts.append('first')
        if operation.get('last'):
            parts.append('last')
        return '-'.join(parts) + ext

    def _sanitize(self, value, key: str = ''):
        """Replace the recording account's project id, emails and caller ip.

        The project id has to go because flight data is recorded against
        the placeholder project (see ``recorder.py``), so an event naming
        the real one would resolve its resource against a project that has
        no recorded responses. Emails and the caller ip are the recording
        developer's, and fixtures are committed.
        """
        if isinstance(value, dict):
            return {k: self._sanitize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize(v, key) for v in value]
        if not isinstance(value, str):
            return value
        if key == 'callerIp':
            return PLACEHOLDER_IP
        return EMAIL_RE.sub(
            PLACEHOLDER_EMAIL, value.replace(self.project_id, PROJECT_ID))

    def _get_entries(self) -> list[dict]:
        session = self.session_factory()
        client = session.client('logging', 'v2', 'entries')
        entries = []
        for page in client.execute_paged_query(
                'list', {'body': self._query_body()}):
            entries.extend(page.get('entries', []))
        return sorted(
            entries,
            key=lambda e: (e.get('timestamp', ''), e.get('insertId', '')),
        )

    def _query_body(self) -> dict:
        project_id = self.project_id
        log_name = 'projects/{}/logs/cloudaudit.googleapis.com%2Factivity'.format(
            project_id)
        filters = [
            'logName = {}'.format(self._quote(log_name)),
            'protoPayload.methodName : {}'.format(self._quote(self.method)),
            'timestamp >= {}'.format(self._quote(self._format_time(self.start_time))),
        ]
        if self.resource_name:
            filters.append(
                'protoPayload.resourceName : {}'.format(self._quote(self.resource_name)))
        for k, v in self.labels.items():
            filters.append('resource.labels.{} = {}'.format(k, self._quote(v)))
        return {
            'resourceNames': ['projects/{}'.format(project_id)],
            'filter': '\n'.join(filters),
            'orderBy': 'timestamp asc',
        }

    def _write_entry(self, event_file: str, payload: str) -> None:
        os.makedirs(EVENT_DIR, exist_ok=True)
        path = os.path.join(EVENT_DIR, event_file)
        index = 0
        while os.path.exists(path):
            index += 1
            path = '{}-{}'.format(os.path.join(EVENT_DIR, event_file), index)
        if index:
            log.warning('GCP audit event fixture collision, wrote %s', path)
        with open(path, 'w') as fh:
            fh.write(payload)

    @staticmethod
    def _format_time(value: datetime.datetime) -> str:
        return value.isoformat().replace('+00:00', 'Z')

    @staticmethod
    def _quote(value: str) -> str:
        return '"{}"'.format(value.replace('\\', '\\\\').replace('"', '\\"'))


class GoogleFlightRecorder(CustodianTestCore):

    data_dir = Path(__file__).parent.parent / 'tests' / 'data' / 'flights'

    def cleanUp(self):
        # Remove the attribute entirely so future checks don't treat a stale
        # None value as a valid cached http client.
        if hasattr(LOCAL_THREAD, 'http'):
            delattr(LOCAL_THREAD, 'http')
        return reset_session_cache()

    def record_flight_data(self, test_case, project_id=None):
        test_dir = os.path.join(self.data_dir, test_case)
        discovery_dir = os.path.join(self.data_dir, "discovery")
        self.recording = True

        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        os.makedirs(test_dir)

        self.addCleanup(self.cleanUp)
        bound = {'http': HttpRecorder(test_dir, discovery_dir)}
        if project_id:
            bound['project_id'] = project_id

        return functools.partial(Session, **bound)

    def replay_flight_data(self, test_case, project_id=None):

        if C7N_FUNCTIONAL:
            self.recording = True
            return functools.partial(Session, project_id=self.project_id)

        if project_id is None:
            project_id = PROJECT_ID

        test_dir = os.path.join(self.data_dir, test_case)
        discovery_dir = os.path.join(self.data_dir, "discovery")
        self.recording = False

        if not os.path.exists(test_dir):
            raise RuntimeError("Invalid Test Dir for flight data %s" % test_dir)

        self.addCleanup(self.cleanUp)
        bound = {
            'http': HttpReplay(test_dir, discovery_dir),
            'project_id': project_id,
        }
        return functools.partial(Session, **bound)


class FlightRecorderTest(TestUtils):

    def cleanUp(self):
        # Remove the attribute entirely so future checks don't treat a stale
        # None value as a valid cached http client.
        if hasattr(LOCAL_THREAD, 'http'):
            delattr(LOCAL_THREAD, 'http')
        return super(FlightRecorderTest, self).cleanUp()

    def record_flight_data(self, test_case, project_id=None):
        test_dir = os.path.join(DATA_DIR, test_case)
        discovery_dir = os.path.join(DATA_DIR, "discovery")
        self.recording = True

        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        os.makedirs(test_dir)

        self.addCleanup(self.cleanUp)
        bound = {'http': HttpRecorder(test_dir, discovery_dir)}
        if project_id:
            bound['project_id'] = project_id
        return functools.partial(Session, **bound)

    def replay_flight_data(self, test_case, project_id=None):
        test_dir = os.path.join(DATA_DIR, test_case)
        discovery_dir = os.path.join(DATA_DIR, "discovery")
        self.recording = False

        if not os.path.exists(test_dir):
            raise RuntimeError("Invalid Test Dir for flight data %s" % test_dir)

        if project_id is None:
            project_id = PROJECT_ID

        self.addCleanup(self.cleanUp)
        bound = {
            'http': HttpReplay(test_dir, discovery_dir),
            'project_id': project_id,
        }
        return functools.partial(Session, **bound)


class BaseTest(FlightRecorderTest):

    custodian_schema = generate()

    @property
    def account_id(self):
        return ""

    @property
    def project_id(self):
        if C7N_FUNCTIONAL:
            return get_default_project()
        return PROJECT_ID
