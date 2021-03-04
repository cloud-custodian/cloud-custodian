# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Supplemental tooling for managing custodian packaging.

Has various workarounds for poetry
"""
from collections import defaultdict
import click
import os
import sys
import toml
from pathlib import Path


@click.group()
def cli():
    """Custodian Python Packaging Utility

    some simple tooling to sync poetry files to setup/pip
    """
    # If there is a global installation of poetry, prefer that.
    poetry_python_lib = os.path.expanduser('~/.poetry/lib')
    sys.path.insert(0, os.path.realpath(poetry_python_lib))
    # poetry env vendored deps
    sys.path.insert(0,
        os.path.join(poetry_python_lib, 'poetry', '_vendor', 'py{}.{}'.format(
            sys.version_info.major, sys.version_info.minor)))


# Override the poetry base template as all our readmes files
# are in markdown format.
#
# Pull request submitted upstream to correctly autodetect
# https://github.com/python-poetry/poetry/pull/1994
#
SETUP_TEMPLATE = """\
# -*- coding: utf-8 -*-
from setuptools import setup

{before}
setup_kwargs = {{
    'name': {name!r},
    'version': {version!r},
    'description': {description!r},
    'long_description': {long_description!r},
    'long_description_content_type': 'text/markdown',
    'author': {author!r},
    'author_email': {author_email!r},
    'maintainer': {maintainer!r},
    'maintainer_email': {maintainer_email!r},
    'url': {url!r},
    {extra}
}}
{after}

setup(**setup_kwargs)
"""


@cli.command()
@click.option('-p', '--package-dir', type=click.Path())
@click.option('-f', '--version-file', type=click.Path())
def gen_version_file(package_dir, version_file):
    data = toml.load(Path(str(package_dir)) / 'pyproject.toml')
    version = data['tool']['poetry']['version']
    with open(version_file, 'w') as fh:
        fh.write('# Generated via tools/dev/poetrypkg.py\n')
        fh.write('version = "{}"\n'.format(version))


@cli.command()
@click.option('-p', '--package-dir', type=click.Path())
def gen_setup(package_dir):
    """Generate a setup suitable for dev compatibility with pip.
    """
    from poetry.core.masonry.builders import sdist
    from poetry.factory import Factory

    factory = Factory()
    poetry = factory.create_poetry(package_dir)

    # the alternative to monkey patching is carrying forward a
    # 100 line method. See SETUP_TEMPLATE comments above.
    sdist.SETUP = SETUP_TEMPLATE

    class SourceDevBuilder(sdist.SdistBuilder):
        # to enable poetry with a monorepo, we have internal deps
        # as source path dev dependencies, when we go to generate
        # setup.py we need to ensure that the source deps are
        # recorded faithfully.

        @classmethod
        def convert_dependencies(cls, package, dependencies):
            reqs, default = super().convert_dependencies(package, dependencies)
            resolve_source_deps(poetry, package, reqs)
            return reqs, default

    builder = SourceDevBuilder(poetry, None, None)
    setup_content = builder.build_setup()

    with open(os.path.join(package_dir, 'setup.py'), 'wb') as fh:
        fh.write(b'# Automatically generated from poetry/pyproject.toml\n')
        fh.write(b'# flake8: noqa\n')
        fh.write(setup_content)


@cli.command()
@click.option('-p', '--package-dir', type=click.Path())
@click.option('-o', '--output', default='setup.py')
def gen_frozensetup(package_dir, output):
    """Generate a frozen setup suitable for distribution.
    """
    from poetry.core.masonry.builders import sdist
    from poetry.factory import Factory

    factory = Factory()
    poetry = factory.create_poetry(package_dir)

    sdist.SETUP = SETUP_TEMPLATE

    class FrozenBuilder(sdist.SdistBuilder):

        @classmethod
        def convert_dependencies(cls, package, dependencies):
            reqs, default = locked_deps(package, poetry)
            resolve_source_deps(poetry, package, reqs, frozen=True)
            return reqs, default

    builder = FrozenBuilder(poetry, None, None)
    setup_content = builder.build_setup()

    with open(os.path.join(package_dir, output), 'wb') as fh:
        fh.write(b'# Automatically generated from pyproject.toml\n')
        fh.write(b'# flake8: noqa\n')
        fh.write(setup_content)


def resolve_source_deps(poetry, package, reqs, frozen=False):
    # find any source path dev deps and them and their recursive
    # deps to reqs
    if poetry.local_config['name'] not in (package.name, package.pretty_name):
        return

    source_deps = []
    for dep_name, info in poetry.local_config.get('dev-dependencies', {}).items():
        if isinstance(info, dict) and 'path' in info:
            source_deps.append(dep_name)
    if not source_deps:
        return

    from poetry.core.packages.dependency import Dependency

    dep_map = {d['name']: d for d in poetry.locker.lock_data['package']}
    seen = set(source_deps)
    seen.add('setuptools')

    prefix = '' if frozen else '^'
    while source_deps:
        dep = source_deps.pop()
        if dep not in dep_map:
            dep = dep.replace('_', '-')
        version = dep_map[dep]['version']
        reqs.append(Dependency(dep, '{}{}'.format(prefix, version)).to_pep_508())
        for cdep, cversion in dep_map[dep].get('dependencies', {}).items():
            if cdep in seen:
                continue
            source_deps.append(cdep)
            seen.add(cdep)


def locked_deps(package, poetry):
    reqs = []
    packages = poetry.locker.locked_repository(False).packages
    for p in packages:
        dep = p.to_dependency()
        line = "{}=={}".format(p.name, p.version)
        requirement = dep.to_pep_508()
        if ';' in requirement:
            line += "; {}".format(requirement.split(";")[1].strip())
        reqs.append(line)
    return reqs, defaultdict(list)


if __name__ == '__main__':
    cli()
