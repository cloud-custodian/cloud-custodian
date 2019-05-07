.. _developer-installing:

Installing for Developers
=========================

Installing Prerequisites
------------------------

Cloud Custodian supports Python 2.7, 3.6, and 3.7.
To develop the Custodian, you will need to have a make/C toolchain, Python 3.7 and some basic Python tools.

We strongly recommend any development be done in Python 3.

Install Python 3.7
~~~~~~~~~~~~~~~~~~

You'll need to have a Python 3.7 environment set up.
You may have a preferred way of doing this.
Here are instructions for a way to do it on Ubuntu and Mac OS X.

On Ubuntu
*********

On most recent versions of Ubuntu, Python 3.6 is included by default.
To get Python 3.7, first add the deadsnakes package repository:

.. code-block:: bash

    $ sudo add-apt-repository ppa:deadsnakes/ppa

Next, install python3.7 and the development headers for it:

.. code-block:: bash

    $ sudo apt-get install python3.7 python3.7-dev

Then, install ``pip``:

.. code-block::

    $ sudo apt-get install python3-pip

When this is complete you should be able to check that you have pip properly installed:

.. code-block::

    $ python3.7 -m pip --version
    pip 9.0.1 from /usr/lib/python3/dist-packages (python 3.7)

(your exact version numbers will likely differ)


On macOS with Homebrew
**********************

.. code-block:: bash

    $ brew install python3

Installing ``python3`` will get you the latest version of Python 3 supported by Homebrew, currently Python 3.7.


Basic Python Tools
~~~~~~~~~~~~~~~~~~

Once your Python installation is squared away, you will need to install ``tox`` and ``virtualenv``:

.. code-block:: bash

    $ python3.7 -m pip install -U pip virtualenv tox

(note that we also updated ``pip`` in order to get the latest version)


Installing Custodian
--------------------

First, clone the repository:

.. code-block:: bash

    $ git clone https://github.com/cloud-custodian/cloud-custodian.git
    $ cd cloud-custodian

Then build the software with `tox <https://tox.readthedocs.io/en/latest/>`_:

.. code-block:: bash

    $ tox

Tox creates a sandboxed "virtual environment" ("virtualenv") for each Python version, 2.7, 3.6, and 3.7.
These are stored in the ``.tox/`` directory.
It then runs the test suite under all versions of Python, per the ``tox.ini`` file.
If tox is unable to find a Python executable on your system for one of the supported versions, it will fail for that environment.
You can safely ignore these failures when developing locally.

You can run the test suite in a single enviroment with the ``-e`` flag:

.. code-block:: bash

    $ tox -e py37

To access the executables installed in one or the other virtual environment,
source the virtualenv into your current shell, e.g.:

.. code-block:: bash

    $ source .tox/py37/bin/activate

You should then have, e.g., the ``custodian`` command available:

.. code-block:: bash

    (py37)$ custodian -h

You'll also be able to invoke `nosetests
<http://nose.readthedocs.io/en/latest/>`_ or `pytest
<https://docs.pytest.org/en/latest/>`_ directly with the arguments of your
choosing, e.g.:

.. code-block:: bash

    (py37) $ pytest tests/test_s3.py -x
