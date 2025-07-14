# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import click
import tomli as toml
from pathlib import Path


@click.group()
def cli():
    """Custodian Python Packaging Utility

    some simple tooling to sync pyproject.toml files to setup/pip
    """


def project_roots(root):
    for config_path in Path(root).rglob("pyproject.toml"):
        yield config_path.parent


@cli.command()
@click.option('-r', '--root', type=click.Path())
@click.option('-o', '--output', type=click.Path())
def gen_qa_requires(root, output):
    packages = []
    for root in project_roots(root):
        data = toml.loads((root / "pyproject.toml").read_text())
        pkg_data = data['project']
        packages.append((pkg_data['name'], pkg_data['version']))

    with open(output, 'w') as fh:
        fh.write("\n".join(
            [f"{name}=={version}" for name, version in packages]))


@cli.command()
@click.option('-p', '--package-dir', type=click.Path())
@click.option('-f', '--version-file', type=click.Path())
def gen_version_file(package_dir, version_file):
    """Generate a version file from pyproject.yml"""
    with open(Path(str(package_dir)) / 'pyproject.toml', 'rb') as f:
        data = toml.load(f)
    version = data['project']['version']
    with open(version_file, 'w') as fh:
        fh.write('# Generated via tools/dev/devpkg.py\n')
        fh.write('version = "{}"\n'.format(version))


if __name__ == '__main__':
    cli()
