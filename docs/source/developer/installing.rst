.. _developer-installing:

Installing for Developers
=========================

Installing Prerequisites
------------------------

Developing the Custodian requires a make/C toolchain, Python 2.7, Python
3.6, and some basic Python tools.

On Ubuntu
~~~~~~~~~

For Python 2.7:

.. code-block:: bash

    $ sudo apt-get install python2.7 python2.7-dev python-pip

Python 3.6 is `more complicated
<https://askubuntu.com/questions/865554/how-do-i-install-python-3-6-using-apt-get>`_.


On macOS with Homebrew
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    $ brew install python python3


Basic Python Tools
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    $ pip install -U pip virtualenv tox


Installing Custodian
--------------------

First, clone the repository:

.. code-block:: bash

    $ git clone https://github.com/cloud-custodian/cloud-custodian.git
    $ cd cloud-custodian

Then build the software with `tox <https://tox.readthedocs.io/en/latest/>`_:

.. code-block:: bash

    $ tox

Tox creates a sandboxed "virtual environment" ("virtualenv") for each Python
version, 2.7 and 3.6. These are stored in the ``.tox/`` directory. It then runs
the test suite under both versions of Python, per the ``tox.ini`` file. You can
run the test suite in a single enviroment with the ``-e`` flag:

.. code-block:: bash

    $ tox -e py27

To access the executables installed in one or the other virtual environment,
source the virtualenv into your current shell, e.g.:

.. code-block:: bash

    $ source .tox/py27/bin/activate

You should then have, e.g., the ``custodian`` command available:

.. code-block:: bash

    (py27)$ custodian -h

You'll also be able to invoke `nosetests
<http://nose.readthedocs.io/en/latest/>`_ or `pytest
<https://docs.pytest.org/en/latest/>`_ directly with the arguments of your
choosing, e.g.:

.. code-block:: bash

    (py27) $ pytest tests/test_s3.py -x
