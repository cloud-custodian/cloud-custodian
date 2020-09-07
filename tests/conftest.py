import pytest

try:
    from .zpill import PillTest
    from c7n.testing import PyTestUtils, reset_session_cache
except ImportError: # noqa
    # docker tests run with minimial deps
    class PyTestUtils:
        pass

    class PillTest:
        pass

try:
    from pytest_terraform.tf import LazyReplay
    LazyReplay.value = True
except ImportError: # noqa
    pass


class CustodianAWSTesting(PyTestUtils, PillTest):
    """Pytest AWS Testing Fixture
    """


@pytest.fixture(scope='function')
def test(request):
    test_utils = CustodianAWSTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils
