.. _gcp_contribute:

Developer Guide
=================

The c7n developer install includes c7n_gcp.  A shortcut for creating a virtual env for development is available
in the makefile:

.. code-block:: bash

    $ make install
    $ source bin/activate

This creates a virtual env in your enlistment and installs all packages as editable.

Instead, you can do `pip install -r tools/c7n_gcp/requirements.txt` to install dependencies.

Adding New GCP Resources
==========================

Load New GCP Resource
---------------------

Once the required dependecies are installed and created the new GCP Resource, custodian will
load all registered resources. Import the resource in
``entry.py``.

.. code-block:: python

    import c7n_gcp.resources.dialogflow

Testing
========

Tests for c7n_gcp run automatically with other Custodian tests. See :ref:`Testing for Developers <developer-tests>` for information on how to run Tox.

Running tests
---------------

You can use `tox` to run all tests or instead you can use `pytest` and run only GCP tests (or only specific set of tests). Running recorded tests still requires some authentication, it is possible to use fake data for credentials to GCP and name of Google Cloud project.

.. code-block:: bash

  export GOOGLE_CLOUD_PROJECT=cloud-custodian
  export GOOGLE_APPLICATION_CREDENTIALS=data/credentials.json
  pytest tools/c7n_gcp/tests

