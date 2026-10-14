.. _developer-release:

Release Process
===============

Prerequisites / Assumptions
---------------------------

* Releases are built and published using the ``main`` branch
* The release process documented here should come _after_ a "release preparation" pull request gets merged. That pull request should:

  * Increment package versions (via ``make pkg-increment``)
  * Update dependencies (via ``make pkg-rebase``)
  * Resolve any test breakages related to those dependency updates

.. note::

    For reference, `here <https://github.com/cloud-custodian/cloud-custodian/pull/7492>`__ is an example pull request preparing for release ``0.9.17.0``.

You'll need `GitHub CLI <https://cli.github.com>`__ and `twine <https://pypi.org/project/twine/>`__ installed as well.

Run Functional Tests
--------------------

Before releasing we run functional tests to ensure trunk is suitable for release:

.. code-block::

    gh workflow run functional.yaml

On success it will notify into the slack channel ``#github-ci``

Release artifact creation
-------------------------

Producing wheels and changelog has been automated via GitHub actions, to create release artifacts:

.. code-block::

    gh workflow run release.yml

This will create wheels, upload them to a private PyPI (AWS Code Artifact), test wheel installation, test basic usage, and generate a changelog.

Download the release artifacts into a clean working copy:

.. code-block::

    make release-get-artifacts

Open the Changelog (``release.md``) in a text editor and adjust accordingly so that it makes sense for humans.

Create a new release on the cloud-custodian repository
------------------------------------------------------

Paste in the changelog when making a release:

.. code-block::

    cat release.md | pbcopy # OSX-only
    cat release.md | xsel -c # Linux/X11 .. for Wayland see wl-clipboard

Create a new tag (such as ``0.9.49.0``):

Github `documentation on managing releases <https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository>`__.

Publish Wheel
-------------

.. code-block::

    make pkg-publish-wheel PKG_REPO=prodpypi

Announce
--------

The release process will automatically publish a notification to the ``#announcements`` channel in
the `community Slack <https://cloudcustodian.io/community/>`__. It is helpful to post in ``#general``
also for visibility.
