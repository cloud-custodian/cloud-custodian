import contextlib
import io

import pytest
from click.testing import CliRunner

from c7n.testing import PyTestUtils


@pytest.fixture(scope="function")
def test(request):
    test_utils = PyTestUtils(request)
    return test_utils


class DebugCliRunner(CliRunner):
    def invoke(self, cli, args=None, **kwargs):
        params = kwargs.copy()
        params["catch_exceptions"] = False
        return super().invoke(cli, args=args, **params)

    @contextlib.contextmanager
    def isolation(self, input=None, env=None, color=False):
        s = io.BytesIO(b"{stdout not captured because --pdb-trace}")
        yield (s, s)


@pytest.fixture
def debug_cli_runner():
    return DebugCliRunner()
