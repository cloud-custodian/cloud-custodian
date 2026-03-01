# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path

import pytest
from c7n_oci.provider import OCI
from oci_common import replace_email, replace_namespace, replace_ocid
from pytest_terraform import tf

from c7n.config import Config
from c7n.testing import PyTestUtils, reset_session_cache
from c7n.vendored.distutils.util import strtobool
from tools.c7n_oci.tests.oci_flight_recorder import OCIFlightRecorder

tf.LazyReplay.value = not strtobool(os.environ.get("C7N_FUNCTIONAL", "no"))
tf.LazyPluginCacheDir.value = "../.tfcache"


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


class CustodianOCITesting(PyTestUtils, OCIFlightRecorder):
    """Pytest OCI Testing Fixture"""


@pytest.fixture(scope="function")
def test(request):
    test_utils = CustodianOCITesting(request)
    return test_utils


@pytest.fixture(scope="function", autouse=True)
def setup(request):
    try:
        oci_provider = OCI()
        oci_provider.initialize(Config.empty())
        yield
    finally:
        reset_session_cache()


@pytest.fixture(params=["WithCompartment", "WithoutCompartment"])
def with_or_without_compartment(request, monkeypatch):
    compartments = None
    if request.param == "WithoutCompartment":
        compartments = os.getenv("OCI_COMPARTMENTS")
        monkeypatch.delenv("OCI_COMPARTMENTS", raising=False)
    yield
    if request.param == "WithoutCompartment":
        monkeypatch.setenv("OCI_COMPARTMENTS", compartments)


def pytest_terraform_modify_state(tfstate):
    tfstate.update(replace_ocid(str(tfstate)))
    tfstate.update(replace_email(str(tfstate)))
    tfstate.update(replace_namespace(str(tfstate)))
