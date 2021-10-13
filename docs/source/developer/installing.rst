.. _developer-installing:

Installing for Developers
=========================

Installing Prerequisites
------------------------

Cloud Custodian supports Python 3.6, 3.7, 3.8 and above. To develop the
Custodian, you will need to have a make/C toolchain, Python3 and some
basic Python tools.


Install Python 3
~~~~~~~~~~~~~~~~

You'll need to have a Python 3 environment set up.
You may have a preferred way of doing this.
Here are instructions for a way to do it on Ubuntu and Mac OS X.

On Ubuntu
*********

On most recent versions of Ubuntu, Python 3 is included by default.

To get Python 3.8, first add the deadsnakes package repository:

.. code-block:: bash

    sudo add-apt-repository ppa:deadsnakes/ppa

Next, install python3.8 and the development headers for it:

.. code-block:: bash

    sudo apt-get install python3.8 python3.8-dev

Then, install ``pip``:

.. code-block::

    sudo apt-get install python3-pip

When this is complete you should be able to check that you have pip properly installed:

.. code-block::

    python3.8 -m pip --version
    pip 9.0.1 from /usr/lib/python3/dist-packages (python 3.8)

(your exact version numbers will likely differ)


On macOS with Homebrew
**********************

.. code-block:: bash

    brew install python3

Installing ``python3`` will get you the latest version of Python 3 supported by Homebrew, currently Python 3.7.


Basic Python Tools
~~~~~~~~~~~~~~~~~~

Once your Python installation is squared away, you will need to install ``tox``:

.. code-block:: bash

    python3.7 -m pip install -U pip tox

(note that we also updated ``pip`` in order to get the latest version)


Installing Custodian
--------------------

First, clone the repository:

.. code-block:: bash

    git clone https://github.com/cloud-custodian/cloud-custodian.git
    cd cloud-custodian

.. note::
    If you have the intention to contribute to Cloud Custodian, it's better to make
    a fork of the Cloud-Custodian repository first, and work inside your fork, so
    that you can push changes to your fork and make a pull request from there. Make
    the fork from the Github UI, then clone your fork instead of the main repository.

    .. code-block:: bash

        git clone https://github.com/<your github account>/cloud-custodian.git

    To keep track of the changes to the original cloud-custodian repository, add a
    remote upstream repository in your fork:

    .. code-block:: bash

        git remote add upstream https://github.com/cloud-custodian/cloud-custodian.git

    Then, to get the upstream changes and merge them into your fork:

    .. code-block:: bash

        git fetch upstream
        git merge upstream/master


Now that the repository is set up, build the software with `tox <https://tox.readthedocs.io/en/latest/>`_:

.. code-block:: bash

    tox

Tox creates a sandboxed "virtual environment" ("venv") for each Python version, 3.6, 3.7, 3.8
These are stored in the ``.tox/`` directory.
It then runs the test suite under all versions of Python, per the ``tox.ini`` file.
If tox is unable to find a Python executable on your system for one of the supported versions, it will fail for that environment.
You can safely ignore these failures when developing locally.

You can run the test suite in a single environment with the ``-e`` flag:

.. code-block:: bash

    tox -e py38

To access the executables installed in one or the other virtual environment,
source the venv into your current shell, e.g.:

.. code-block:: bash

    source .tox/py37/bin/activate

You should then have, e.g., the ``custodian`` command available:

.. code-block:: bash

    (py37)$ custodian -h

You'll also be able to invoke `pytest <https://docs.pytest.org/en/latest/>`_ directly
with the arguments of your choosing, e.g.:

.. code-block:: bash

    (py37) $ pytest tests/test_s3.py -x -k replication

Note that you'll have to set up environment variables appropriately per the tox.ini
for provider credentials. See below for the best way to do that.


Installing in Your Own Virtual Environment
------------------------------------------

Running directly from a tox sandbox, while very easy to set up, might not be
the most comfortable way of working. You might want to create your own virtual
environment and use that for running Custodian. This can be done using the ``venv``
module. It can be done right inside the cloned Cloud Custodian repository:

.. code-block:: bash

    python3 -m venv .

The above command assumes the current directory is the Cloud Custodian checkout.

Next, you'll need to install all the development dependencies. Cloud Custodian uses
`poetry <https://python-poetry.org>`_ for packaging and dependency management.
Poetry uses a custom installer, to be fully isolated from the rest of your system.

For osx and linux, poetry recommends running this for installing:

.. code-block:: bash

    curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python -

For windows powershell use this command:

.. code-block:: bash

    (Invoke-WebRequest -Uri https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py -UseBasicParsing).Content | python -


Once poetry is installed, you can set up Cloud Custodian using the included Makefile:

.. code-block:: bash

    source bin/activate
    (cloud-custodian) $ make install-poetry

.. note::
    It's important to activate the venv before running the installer, or poetry will
    create a venv for each dependency folder included in the Cloud Custodian repository.

Once this is done, poetry can be used to run the tests as well:

.. code-block:: bash

    (cloud-custodian) $ make test-poetry

You could also use ``pytest`` to run the tests, but you will need to set up some
environment variables to successfully run the full test suite. The best way to do
that is to edit the ``test.env`` file in the root of the repository and "source" it,
using the shell:

.. code-block:: bash

    source test.env

In general, it's best to use ``tox`` to run the full test suite, and use ``pytest``
to run specific tests that you are working on.