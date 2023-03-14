# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from c7n.testing import PyTestUtils, reset_session_cache
from zpill import PillTest


class CloudControlTesting(PyTestUtils, PillTest):
    """Pytest AWS Testing Fixture"""

    placebo_dir = Path(__file__).absolute().parent / "data" / "placebo"


@pytest.fixture(scope="function")
def test_awscc(request):
    test_utils = CloudControlTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils
