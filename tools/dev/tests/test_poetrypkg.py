import subprocess
import sys

import pytest

from pathlib import Path

from click.testing import CliRunner

cli = Path(__file__).parent.parent / "poetrypkg.py"
with open(cli, encoding='utf-8') as f:
    exec(f.read())

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


def _assert_pkg_ok(
    runner, pkg, command='gen-frozensetup', check_file='setup.py',
    cached=False, check_diff=True
):
    base = Path(__file__).parent.parent.parent.parent / pkg

    with open(base / check_file) as f:
        original = f.read()

    result = runner.invoke(cli, [command, '-p', base])
    assert result.exit_code == 0
    cached = ' --cached ' if cached else ' '

    if not check_diff:
        return

    git_diff_command = list(f"git diff{cached}{base}/{check_file}".split(' '))
    diff = subprocess.check_output(
        git_diff_command,
        stderr=subprocess.STDOUT,
    )
    # we should get a git diff as a result of running the command
    assert diff

    if cached == ' --cached':
        # clean up the git diff
        subprocess.run(f'git rm --cached {check_file}'.split(' '))

    # clean up the setup.py file for a clean diff
    with open(base / check_file, "w") as f:
        f.write(original)


@pytest.mark.skipif(sys.version_info <= (3, 8), reason="Developer Python minimum is 3.8")
@pytest.mark.skipif(sys.platform == 'win32', reason="No Windows support")
def test_generate_frozen_deps():
    """
    Ensures that the gen-frozendeps command works and creates a git diff
    """

    runner = CliRunner()

    for pkg in PKG_SET:
        _assert_pkg_ok(runner, pkg)


@pytest.mark.skipif(sys.version_info <= (3, 8), reason="Developer Python minimum is 3.8")
@pytest.mark.skipif(sys.platform == 'win32', reason="No Windows support")
def test_generate_setup():
    """
    Ensures that the gen-setup command works
    """

    runner = CliRunner()

    for pkg in PKG_SET:
        _assert_pkg_ok(
            runner, pkg, check_file='poetry.lock',
            command='gen-setup', cached=True, check_diff=False
        )
