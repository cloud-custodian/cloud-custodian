# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest

from pytest_terraform.tf import LazyPluginCacheDir, LazyReplay

from c7n.testing import PyTestUtils, reset_session_cache, C7N_FUNCTIONAL
from c7n_gcp.client import get_default_project

from gcp_common import GoogleFlightRecorder, PROJECT_ID
from recorder import sanitize_project_name

LazyReplay.value = not C7N_FUNCTIONAL
LazyPluginCacheDir.value = '../.tfcache'


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
