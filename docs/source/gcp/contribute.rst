.. _gcp_contribute:

Developer Guide
===============

The c7n developer install includes c7n_gcp.  A shortcut for creating a virtual env for development is available
in the makefile:

.. code-block:: bash

    $ make install
    $ source bin/activate

This creates a virtual env in your enlistment and installs all packages as editable.

Instead, you can do `pip install -r tools/c7n_gcp/requirements.txt` to install test dependencies.

Adding New GCP Resources
==========================

Install GCP Dependencies
--------------------------

Custodian interfaces with ARM resources using Azure's SDKs.
Install the resources SDK in ``setup.py``.

Create New GCP Resource
-------------------------

Create your new Azure Resource.

- ``service``: The Azure SDK dependency added in step 1.
- ``client``: Client class name of the Azure Resource SDK of the resource you added.
- ``enum_spec``: Is a tuple of (enum_operation, list_operation, extra_args). The resource SDK client will have a list of operations this resource has.
    Place the name of the property as the enum_operation. Next, put `list` as the operations.

.. code-block:: python

    from c7n_gcp.provider import resources


Load New GCP Resource
-----------------------

Once the required dependecies are installed and created the new GCP Resource, custodian will
load all registered resources. Import the resource in
``entry.py``.

.. code-block:: python

    import c7n_gcp.resources.container_registry

Testing
=======

Tests for c7n_gcp run automatically with other Custodian tests.  See :ref:`Testing for Developers <developer-tests>`
for information on how to run Tox.


Running tests
-------------

You can use `tox` to run all tests or instead you can use `pytest` and run only GCP tests (or only specific set of tests). Runing recorded tests still requires some authentication, it is possible to use fake data for authorization token and subscription id.

.. code-block:: bash

  export GOOGLE_CLOUD_PROJECT=cloud-custodian
  export GOOGLE_APPLICATION_CREDENTIALS=data/credentials.json
  pytest tools/c7n_gcp/tests
