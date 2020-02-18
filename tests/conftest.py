import pytest

from .zpill import PillTest
from c7n.testing import PyTestUtils, reset_session_cache


class CustodianAWSTesting(PyTestUtils, PillTest):
    """Pytest AWS Testing Fixture
    """


@pytest.fixture(scope='function')
def test(request):
    test_utils = CustodianAWSTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils
