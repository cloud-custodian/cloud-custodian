# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os
from distutils.util import strtobool

import pytest
from pytest_terraform import tf

from c7n.testing import PyTestUtils, reset_session_cache
from oci_common import replace_ocid, replace_email, replace_namespace
from tools.c7n_oci.tests.oci_flight_recorder import OCIFlightRecorder

tf.LazyReplay.value = not strtobool(os.environ.get("C7N_FUNCTIONAL", "no"))
tf.LazyPluginCacheDir.value = "../.tfcache"


class CustodianOCITesting(PyTestUtils, OCIFlightRecorder):
    """Pytest OCI Testing Fixture"""


@pytest.fixture(scope="function")
def test(request):
    test_utils = CustodianOCITesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils


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
