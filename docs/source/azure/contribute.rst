.. _azure_contribute:

Developer Guide
===============

The c7n developer install includes c7n_azure.  A shortcut for creating a virtual env for development is available
in the makefile:

.. code-block:: bash

    $ make install
    $ source bin/activate

This creates a virtual env in your enlistment and installs all packages as editable.


Testing
-------

Tests for c7n_azure run automatically with other Custodian tests.  See :ref:`Testing for Developers <developer-tests>`
for information on how to run Tox.

Azure tests are based on `VCR.py <https://vcrpy.readthedocs.io/en/latest/>`_.
