.. _developer-packaging:

Packaging Custodian
===================

Custodian uses ``UV`` https://docs.astral.sh/uv/ for
managing dependencies and providing for repeatable installs. Its not
typically required for developers as we maintain setuptools/pip
compatible environments, however familiarity is needed when making
changes to the dependency graph (add/update/remove) dependencies,
as all the setup.py/requirements files are generated artifacts.

The reasoning around the move to uv was that of needing better
tooling to freeze the custodian dependency graph when publishing
packages to pypi to ensure that releases would be repeatably
installable at a future date in spite of changes to the underlying
dependency graph, some perhaps not obeying semantic versioning
principles. Additionally, with the growth of providers and other tools,
we wanted better holistic management for release automation across the
set of packages. After experimenting with a few tools in the
ecosystem, including building our own, the maintainers settled on
uv as one that offered both a superior ux, was actively
maintained, and had a reasonable python api for additional release
management activities.

Usage
-----
We maintain several makefile targets that can be used to front end
uv.

  - `make install` installs custodian using uv.

  - `make pkg-increment` update all project versions

  - `make pkg-rebase` update dependencies across projects

  - `make pkg-build-wheel` build wheels and lint for all projects

  - `make pkg-publish-wheel` publish previously built wheels for all projects


Caveats
-------

To maintain dependencies between packages within our repository, we
specify all intra repo dependencies as dev dependencies with relative
directory source paths. Our wheel building process converts the dev
path dependency to a released version reference as a regular dependency.

Currently a result of this process we only publish wheels instead of sdists
as the later don't contain the intra repo dependencies.
