import pytest

from c7n.testing import PyTestUtils


@pytest.fixture(scope="function")
def test(request):
    test_utils = PyTestUtils(request)
    return test_utils
