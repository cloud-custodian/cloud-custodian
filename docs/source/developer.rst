.. _developer:

Developer Install and Testing
=============================

Requirements
------------

The Custodian requires Python 2.7, and a make/C toolchain.

On Linux
~~~~~~~~

.. code-block:: bash

   sudo apt-get install python python-dev python-pip python-virtualenv

On Mac
~~~~~~

.. code-block:: bash

   brew install python

Installing
----------

First, clone the repository:

.. code-block:: bash

   $ git clone https://github.com/capitalone/cloud-custodian.git
   $ cd cloud-custodian

Then build the software:

.. code-block:: bash

   $ make develop

Once that completes, make sure you load the virtualenv into your current shell:

.. code-block:: bash

   $ source bin/activate

You should have the ``custodian`` command available now:

.. code-block:: bash

   $ custodian -h

Running tests
-------------

Unit tests can be run with:

.. code-block:: bash

   $ make test

Coverage reports can be generated and viewed with the following:

.. code-block:: bash

   $ make coverage

   # Open the reports in a browser

   # on osx
   $ open coverage/index.html

   # on gnomeish linux
   $ gnome-open coverage/index.html
