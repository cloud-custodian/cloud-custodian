# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import functools
import json
import os
import shutil

from pathlib import Path

from c7n.schema import generate
from c7n.testing import (
    CustodianTestCore,
    TestUtils,
    reset_session_cache,
    C7N_FUNCTIONAL,
)

from c7n_gcp.client import Session, LOCAL_THREAD

from recorder import (
    HttpRecorder,
    HttpReplay,
    PROJECT_ID,
)


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'flights')
EVENT_DIR = os.path.join(os.path.dirname(__file__), 'data', 'events')


def event_data(fname):
    with open(os.path.join(EVENT_DIR, fname)) as fh:
        return json.load(fh)


class GoogleFlightRecorder(CustodianTestCore):

    data_dir = Path(__file__).parent.parent / 'tests' / 'data' / 'flights'

    def cleanUp(self):
        LOCAL_THREAD.http = None
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
            if not project_id:
                return Session
            return functools.partial(Session, project_id=project_id)

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
        LOCAL_THREAD.http = None
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
