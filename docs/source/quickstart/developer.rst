Developer Install
=================


Requirements
------------

- Ensure proxy is configured properly

On Linux
~~~~~~~~

.. code-block:: bash

   sudo apt-get install python python-dev python-pip python-virtualdev

On Mac
~~~~~~

.. code-block:: bash

   brew install python

Installing
----------

First, clone the repository:

.. code-block:: bash

   $ git clone https://github.com/capitalone/cloud-custodian.git

Also recommended is to use a virtualenv to sandbox this install from your system packages:

.. code-block:: bash

   $ virtualenv cloud-custodian
   $ source cloud-custodian/bin/activate

And then install the dependencies. Deployed systems will just use `requirements.txt`; you'll need the additional testing libraries in `requirements-dev.txt`.

.. code-block:: bash

   $ pip install -r requirements-dev.txt

And then the maid itself

.. code-block:: bash

   $ python setup.py develop

You should have the cloud-maid command available now.

.. code-block:: bash

   $ custodian -h
 
Alternatively, you can just run the commands below 

.. code-block:: bash

   $ cd cloud-custodian
   $ make install
   $ ./bin/custodian -h

Running tests
-------------

There are several additional dependencies for running unit tests.

.. code-block:: bash

   $ cd cloud-maid
   $ make install

And then unit tests can be run with

.. code-block:: bash

   $ make test

Coverage reports can be generated and viewed with the following.

.. code-block:: bash

   $ make coverage

   # Open the reports in a browser

   # on osx
   $ open coverage/index.html

   # on gnomeish linux
   $ gnome-open coverage/index.html
