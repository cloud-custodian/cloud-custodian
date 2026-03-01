# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path

import pytest
from c7n_gcp.client import get_default_project
from c7n_gcp.region import Region
from gcp_common import PROJECT_ID, GoogleFlightRecorder
from pytest_terraform.tf import LazyPluginCacheDir, LazyReplay
from recorder import sanitize_project_name

from c7n.testing import C7N_FUNCTIONAL, PyTestUtils, reset_session_cache
from c7n.utils import jmespath_search

LazyReplay.value = not C7N_FUNCTIONAL
LazyPluginCacheDir.value = '../.tfcache'


@pytest.fixture(autouse=True, scope="session")
def set_working_directory():
    original_cwd = os.getcwd()
    # The OCI_KEY_FILE environment variable has a path relative to
    # the root of the repository. Tests _usually_ run with that as
    # the cwd, but force that here to avoid failures when pytest
    # runs from elsewhere.
    os.chdir(Path(__file__).parent.parent.parent.parent)
    print(f"Changed working directory to {os.getcwd()} for tests")
    yield
    os.chdir(original_cwd)


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

    @staticmethod
    def check_report_fields(policy, resources):
        for f in policy.resource_manager.resource_type.default_report_fields:
            for r in resources:
                assert jmespath_search(f, r) is not None, f"Invalid Report Field {f}"

    def set_regions(self, regions):
        Region.set_regions(regions)
        self.addCleanup(Region.set_regions, None)


@pytest.fixture(scope='function')
def test(request):
    test_utils = CustodianGCPTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils


def pytest_terraform_modify_state(tfstate):
    """ Sanitize functional testing account data """
    tfstate.update(sanitize_project_name(str(tfstate)))
