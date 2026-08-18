# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import functools
import json
import logging
import os
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


def event_data(fname):
    with open(os.path.join(EVENT_DIR, fname)) as fh:
        return json.load(fh)


def audit_event_recorder(
        session_factory,
        event_file: str,
        method: str,
        resource_name: typing.Optional[str] = None,
        labels: typing.Optional[typing.Mapping[str, str]] = None,
        start_time_skew: int = 60,
        timeout: int = 120,
        poll_interval: int = 5,
):
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
        start_time_skew=start_time_skew,
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
            start_time_skew: int = 60,
            timeout: int = 120,
            poll_interval: int = 5,
    ):
        self.session_factory = session_factory
        self.event_file = event_file
        self.method = method
        self.resource_name = resource_name
        self.labels = labels or {}
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.start_time = (
            datetime.datetime.now(datetime.timezone.utc) -
            datetime.timedelta(seconds=start_time_skew)
        )

    def record(self) -> None:
        deadline = time.time() + self.timeout
        operation_index: dict = {}
        while True:
            entries = self._get_entries()
            if entries:
                if self._write_batch(entries, operation_index):
                    return
            if time.time() >= deadline:
                raise AssertionError(
                    'No GCP audit log entries matched {}'.format(self.event_file))
            time.sleep(self.poll_interval)

    def _write_batch(self, entries: list[dict], operation_index: dict) -> bool:
        """Write one poll batch. Returns True when polling should stop."""
        stop = False
        for entry in entries:
            operation = entry.get('operation') or {}
            operation_id = operation.get('id')
            if not operation_id:
                self._write_entry(self.event_file, entry)
                stop = True
                continue
            if operation_id not in operation_index:
                operation_index[operation_id] = len(operation_index)
            index = operation_index[operation_id]
            self._write_entry(
                self._operation_file_name(index, operation), entry)
            if operation.get('last'):
                stop = True
        return stop

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

    def _get_entries(self) -> list[dict]:
        session = self.session_factory()
        client = session.client('logging', 'v2', 'entries')
        response = client.execute_query('list', {'body': self._query_body(session)})
        return sorted(
            response.get('entries', []),
            key=lambda e: (e.get('timestamp', ''), e.get('insertId', '')),
        )

    def _query_body(self, session) -> dict:
        project_id = session.get_default_project()
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

    def _write_entry(self, event_file: str, entry: dict) -> None:
        os.makedirs(EVENT_DIR, exist_ok=True)
        path = os.path.join(EVENT_DIR, event_file)
        if os.path.exists(path):
            index = 1
            while os.path.exists('{}-{}'.format(path, index)):
                index += 1
            path = '{}-{}'.format(path, index)
            log.warning('GCP audit event fixture collision, wrote %s', path)
        with open(path, 'w') as fh:
            json.dump(entry, fh, indent=2, sort_keys=True)
            fh.write('\n')

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
