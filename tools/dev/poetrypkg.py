# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import click
import tomli as toml
from pathlib import Path


@click.group()
def cli():
    """Custodian Python Packaging Utility

    some simple tooling to sync poetry files to setup/pip
    """

@cli.command()
@click.option('-p', '--package-dir', type=click.Path())
@click.option('-f', '--version-file', type=click.Path())
def gen_version_file(package_dir, version_file):
    """Generate a version file from poetry"""
    with open(Path(str(package_dir)) / 'pyproject.toml', 'rb') as f:
        data = toml.load(f)
    version = data['tool']['poetry']['version']
    with open(version_file, 'w') as fh:
        fh.write('# Generated via tools/dev/poetrypkg.py\n')
        fh.write('version = "{}"\n'.format(version))


if __name__ == '__main__':
    cli()
