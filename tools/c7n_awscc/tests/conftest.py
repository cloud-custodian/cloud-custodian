from pathlib import Path
import sys

import pytest
from c7n.testing import PyTestUtils, reset_session_cache


def init_c7n_fixture():
    root = Path("__file__").parent.parent
    c7n_tests = root / "tests"
    sys.path.append(str(c7n_tests.absolute()))


init_c7n_fixture()

from zpill import PillTest  # noqa


class CustodianAWSTesting(PyTestUtils, PillTest):
    """Pytest AWS Testing Fixture"""


@pytest.fixture(scope="function")
def test(request):
    test_utils = CustodianAWSTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils
