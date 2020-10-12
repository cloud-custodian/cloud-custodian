# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest
import functools
import os
import shutil

from c7n.testing import PyTestUtils, reset_session_cache, CustodianTestCore
from c7n_gcp.client import Session, get_default_project, LOCAL_THREAD
from recorder import sanitize_project_name, PROJECT_ID, HttpRecorder, HttpReplay
from distutils.util import strtobool
from pytest_terraform.tf import LazyPluginCacheDir, LazyReplay


IS_C7N_FUNCTIONAL = strtobool(os.environ.get('C7N_FUNCTIONAL', 'no'))

# If we have C7N_FUNCTIONAL make sure Replay is False otherwise enable Replay
LazyReplay.value = not IS_C7N_FUNCTIONAL
LazyPluginCacheDir.value = '../.tfcache'


class GoogleFlightRecorder(CustodianTestCore):

    data_dir = os.path.join(os.path.dirname(__file__), 'data', 'flights')

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

        if IS_C7N_FUNCTIONAL:
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


class CustodianGCPTesting(PyTestUtils, GoogleFlightRecorder):
    @property
    def project_id(self):
        try:
            if not self.recording:
                return PROJECT_ID
        except AttributeError:
            raise RuntimeError('project_id not available until after '
                               'replay or record flight data is invoked')
        return get_default_project()


@pytest.fixture(scope='function')
def test(request):
    test_utils = CustodianGCPTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils


def pytest_terraform_modify_state(tfstate):
    """ Sanitize functional testing account data """
    tfstate.update(sanitize_project_name(str(tfstate)))
