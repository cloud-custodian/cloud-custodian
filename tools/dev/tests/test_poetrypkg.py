import subprocess
import sys

import pytest

from pathlib import Path

from click.testing import CliRunner

cli = Path(__file__).parent.parent / "poetrypkg.py"
with open(cli, encoding='utf-8') as f:
    exec(f.read())


@pytest.mark.skipif(sys.version_info <= (3, 8), reason="Developer Python minimum is 3.8")
def test_generate_frozen_deps():
    """
    Ensures that the gen-frozendeps command works and creates a git diff
    """

    def _assert_pkg_ok(pkg):
        base = Path(__file__).parent.parent.parent.parent / pkg

        with open(base / "setup.py") as f:
            original = f.read()

        result = runner.invoke(cli, ['gen-frozensetup', '-p', base])
        assert result.exit_code == 0
        gitdiff = subprocess.check_output(
            f"git diff {base}/setup.py".split(' '),
            stderr=subprocess.STDOUT,
        )
        # not the most exact check, but at the end of generating the frozen
        # deps the git diff should have changed
        assert gitdiff

        # clean up the setup.py file for a clean diff
        with open(base / "setup.py", "w") as f:
            f.write(original)

    PKG_SET = (
        '.',
        'tools/c7n_gcp',
        'tools/c7n_kube',
        'tools/c7n_openstack',
        'tools/c7n_mailer',
        'tools/c7n_logexporter',
        'tools/c7n_policystream',
        'tools/c7n_trailcreator',
        'tools/c7n_org',
        'tools/c7n_sphinxext',
        'tools/c7n_terraform',
        'tools/c7n_awscc',
        'tools/c7n_tencentcloud',
        'tools/c7n_azure',
    )
    runner = CliRunner()

    for pkg in PKG_SET:
        _assert_pkg_ok(pkg)
