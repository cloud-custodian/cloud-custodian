.. _developer-installing:

Installing for Developers
=========================

Installing Prerequisites
------------------------

Cloud Custodian supports Python 3.7 and above. To work on Custodian's code base, you will need:

* A make/C toolchain
* A supported release of Python 3
* Some basic Python tools


Install Python 3
~~~~~~~~~~~~~~~~

You'll need to have a Python 3 environment set up.
You may have a preferred way of doing this.
Here are instructions for a way to do it on Ubuntu and Mac OS X.

On Ubuntu
*********

Python 3 is included in recent Ubuntu releases.

To install Ubuntu's default Python 3 version along with additional packages required
to manage Python packages and environments, run:

.. code-block:: bash

    sudo apt-get install python3 python3-venv python3-pip

When this is complete you should be able to check that you have pip properly installed:

.. code-block::

    python3 -m pip --version
    pip 20.0.2 from /usr/lib/python3/dist-packages/pip (python 3.8)

(your exact version numbers will likely differ)


On macOS with Homebrew
**********************

.. code-block:: bash

    brew install python3

Installing ``python3`` will get you the latest version of Python 3 supported by Homebrew, currently Python 3.9.


On Windows
**********

The Windows Store provides `apps <https://www.microsoft.com/en-us/search/shop/apps?q=python&devicetype=pc&category=Developer+tools%5cDevelopment+kits>`_
for active Python 3 releases.


Other Installation Methods
**************************

If ``python3 --version`` shows a Python version that is not
`actively supported <https://devguide.python.org/#status-of-python-branches>`_ and the steps
above don't apply to your environment, you can still install a current release of Python
manually. `This guide <https://realpython.com/installing-python/>`_ may be a useful reference.


Install UV
~~~~~~~~~~~~~~

Cloud Custodian uses `UV <https://docs.astral.sh/uv/>`_ to manage Python and its dependencies. 
You will need to install `install UV <https://docs.astral.sh/uv/getting-started/installation/>`_.

On Mac/Linux
************

.. code-block:: bash

    curl -LsSf https://astral.sh/uv/install.sh | sh

On Windows with Powershell
**************************

.. code-block:: powershell

    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

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
        git merge upstream/main


Now that the repository is set up, perform a developer installation using UV:

.. code-block:: bash

    make install

This creates a sandboxed "virtual environment" ("venv") inside the ``cloud-custodian``
directory, and installs the full suite of Cloud Custodian packages.

You can run tests via UV as well:

.. code-block:: bash

    make test

To run executables from your UV environment, precede them with ``uv run``:

.. code-block:: bash

   uv run custodian version

Alternatively, activate a UV virtualenvment shell so that commands will run from your
development environment by default:

.. code-block:: bash

    source .venv/bin/activate
    custodian version
    custodian schema

You'll also be able to invoke `pytest <https://docs.pytest.org/en/latest/>`_ directly
with the arguments of your choosing, though that requires mimicking ``make test``'s
environment preparation:

.. code-block:: bash

    source .venv/bin/activate
    source test.env
    pytest tests/test_s3.py -x -k replication
