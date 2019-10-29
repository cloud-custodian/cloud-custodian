import pytest

from .common import C7N_SCHEMA, ACCOUNT_ID
from .zpill import PillTest
from c7n.testing import PyTestUtils, reset_session_cache


class CustodianAWSTesting(PyTestUtils, PillTest):

    custodian_schema = C7N_SCHEMA

    @property
    def account_id(self):
        return ACCOUNT_ID


@pytest.fixture(scope='function')
def test(request):
    test_utils = CustodianAWSTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils
