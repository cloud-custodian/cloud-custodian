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

Install GCP Dependencies
--------------------------

Custodian interfaces uses GCP's REST interface.

Create New GCP Resource (Need to check)
-----------------------------------------

Create your new GCP Resource.

- ``service``: The GCP SDK dependency added in step 1.
- ``client``: Client class name of the Azure Resource SDK of the resource you added.
- ``enum_spec``: Is a tuple of (enum_operation, list_operation, extra_args). The resource SDK client will have a list of operations this resource has.
    Place the name of the property as the enum_operation. Next, put `list` as the operations.

.. code-block:: python

    from c7n_gcp.provider import resources


Load New GCP Resource (Need to check)
--------------------------------------

Once the required dependecies are installed and created the new GCP Resource, custodian will
load all registered resources. Import the resource in
``entry.py``.

.. code-block:: python

    import c7n_gcp.resources.container_registry

Testing (Need to check)
=========================

Tests for c7n_gcp run automatically with other Custodian tests.
for information on how to run Tox.


Running tests
---------------

You can use `tox` to run all tests or instead you can use `pytest` and run only GCP tests (or only specific set of tests). Running recorded tests still requires some authentication, it is possible to use fake data for credentials to GCP and name of Google Cloud project.

.. code-block:: bash

  export GOOGLE_CLOUD_PROJECT=cloud-custodian
  export GOOGLE_APPLICATION_CREDENTIALS=data/credentials.json
  pytest tools/c7n_gcp/tests
