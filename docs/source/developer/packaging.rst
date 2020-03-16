.. _developer-packaging:

Packaging Custodian
===================

Custodian uses ``poetry`` https://python-poetry.org/ for
managing dependencies and providing for repeatable installs. Its not
typically required for developers as we maintain setuptools/pip/tox
compatible environments, however familiarity is needed when making
changes to the dependency graph (add/update/remove) dependencies,
as all the setup.py/requirements files are generated artifacts.

The reasoning around the move to poetry was that of needing better
tooling to freeze the custodian dependency graph when publishing
packages to pypi to ensure that releases would be repeatably
installable at a future date inspite of changes to the underlying
dependency graph, some perhaps not obeying semantic versioning
principles. Additionally with the growth of providers and other tools,
we wanted better holistic management for release automation across the
set of packages. After experimenting with a few tools in the
ecosystem, including building our own, the maintainers settled on
poetry as one that offered both a superior ux, was actively
maintained, and had a reasonable python api for additional release
management activities.

Our additional tooling around poetry is to help automate management
across the half-dozen custodian packages as well as to keep
requirements and setup.py files in sync. We continue to use
setuptools/pip in our CI infrastructure as it offers significant speed
benefits [0]. To ensure the poetry install is exercised as part of CI,
we do maintain the main docker image via poetry.

Usage
-----

We maintain several makefile targets that can be used to front end
poetry.

  - `make install-poetry` an alternative custodian installation method, assumes
    poetry is already installed.

  - `make pkg-show-update` show available updates to packages in poetry
    lockfiles.

  - `make pkg-update` attempts to update dependencies across the tree,
    should be followed by gen-requirements/gen-setup below.

  - `make pkg-gen-requirements` show available updates to packages in poetry
    lockfiles.

  - `make pkg-gen-setup` generate setup.py files from pyproject.toml
    this will carry over semver constraints.

  - `make pkg-freeze-setup` generate setup.py files from pyproject.toml
    with all dependencies frozen in setup.py.

  - `make pkg-publish-wheel` increments version, builds wheels, lints,
    and publishes build to testpypi via twine.

The underlying script that provides additional poetry/packaging
automation specific to custodian is in tools/dev/poetrypkg.py

- [0] poetry will call out to pip as a subprocess per package to
  control the exact versions installed, as pip does not have a public
  api.


Caveats
-------

To maintain within repo dependencies betweeen packages, we specify all
within intra repo dependencies as dev dependencies with relative
directory source paths. When we generate setup.py files we do so sans
any dev deps, which we resolve in generation to the latest version,
frozen or semver compatible per source dir dev dep.

One interesting consequence of source directory dependencies in poetry
is that break any attempts to distribute/publish a package even if
they are `dev` deps. ie. per the pyproject.toml spec is that via the
build-system PEP, poetry will be invoked during install. The
invocation/installation of poetry as a build sys is transparently
handled by pip.  Simple resolution/parse of pyproject.toml dev
dependencies will cause a poetry failure for an source distribution
install, as installation of an sdist, is actually a wheel
compilation.

As a result of this as a publishing limitation we only publish wheels
instead of sdists which avoids the build system entirely, as a wheel
is extractable installation container/format file.
