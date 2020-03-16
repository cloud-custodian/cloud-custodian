"""
Supplemental tooling for managing custodian depgraph

"""
import click
import os
import sys

from collections import defaultdict
from pathlib import Path
from pip._internal.utils import appdirs


@click.group()
def cli():
    """Custodian Python Packaging Utility

    some simple tooling to sync poetry files to setup/pip
    """
    # If there is a global installation of poetry, prefer that.
    poetry_python_lib = os.path.expanduser('~/.poetry/lib')
    sys.path.append(os.path.realpath(poetry_python_lib))


@cli.command()
@click.option('--cache', default=appdirs.user_cache_dir('pip'))
@click.option('--link-dir', type=click.Path())
def gen_links(cache, link_dir):
    # wheel only
    #
    # generate a find links directory to perform an install offline.
    # note there we still need to download any packages needed for
    # an offline install. this is effectively an alternative to
    # pip download -d to utilize already cached wheel resources.
    #
    found = {}
    link_dir = Path(link_dir)
    wrote = 0
    for root, dirs, files in os.walk(cache):
        for f in files:
            if not f.endswith('whl'):
                continue
            found[f] = os.path.join(root, f)
    if not link_dir.exists():
        link_dir.mkdir()
    entries = {f.name for f in link_dir.iterdir()}
    for f, src in found.items():
        if f in entries:
            continue
        os.symlink(src, link_dir / f)
        wrote += 1
    if wrote:
        print('Updated %d Find Links' % wrote)


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
def gen_setup(package_dir):
    """Generate a setup suitable for dev compatibility with pip.
    """
    from poetry.masonry.builders import sdist
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
    from poetry.masonry.builders import sdist
    from poetry.factory import Factory

    factory = Factory()
    poetry = factory.create_poetry(package_dir)

    sdist.SETUP = SETUP_TEMPLATE

    # the alternative to monkey patching is carrying forward a
    # 100 line method. See SETUP_TEMPLATE comments above.
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

    from poetry.packages.dependency import Dependency

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
