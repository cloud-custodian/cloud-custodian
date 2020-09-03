import re
import os
import pytest

from .constants import ACCOUNT_ID
from distutils.util import strtobool

try:
    from .zpill import PillTest
    from c7n.testing import PyTestUtils, reset_session_cache
    from pytest_terraform.tf import LazyPluginCacheDir, LazyReplay
except ImportError: # noqa
    # docker tests run with minimial deps
    class PyTestUtils:
        pass

    class PillTest:
        pass

    class LazyReplay:
        pass

    class LazyPluginCacheDir:
        pass


# If we have C7N_FUNCTIONAL make sure Replay is False otherwise enable Replay
LazyReplay.value = not strtobool(os.environ.get('C7N_FUNCTIONAL', 'no'))
LazyPluginCacheDir.value = '../.tfcache'


class CustodianAWSTesting(PyTestUtils, PillTest):
    """Pytest AWS Testing Fixture
    """


@pytest.fixture(scope='function')
def test(request):
    test_utils = CustodianAWSTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils


def pytest_terraform_modify_state(tfstate):
    """ Sanitize functional testing account data """
    tfstate.update(re.sub(r'([0-9]+){12}', ACCOUNT_ID, str(tfstate)))
