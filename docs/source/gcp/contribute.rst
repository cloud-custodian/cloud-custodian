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

Create New GCP Resource
-------------------------

Most resources extend the QueryResourceManager class. Each class definition will use the @resources.register('<resource_name>') decorator to register that class as a Custodian resource substituting <resource_name> with the new resource name. The name specified in the decorator is how the resource will be referenced within policies.

Each resource also contains an internal class called resource_type, which contains metadata about the resource definition, and has the following attributes:


- ``service`` is required field, part of the request to GCP resource,
    The name of GCP service.
- ``component`` is required field, part of the request to GCP resource,
    The name of GCP resource,
- ``version`` is required field,
    It is the version of used resource API, part of the request to GCP resource,
- ``enum_spec`` is a tuple of (enum_operation, list_operation, extra_args), required field,
    Place the name of the GCP resource method as the enum_operation.
    Next, put path to searching array on the list_operation place.
    Extra_args can be used for set up additional params to a request to GCP.
- ``id`` is required field,
    It uses the field as id of the resource,
- ``scope`` is optional field, default is None,
    The scope of the resource,
- ``parent_spec`` is an optional field for build additional requests, default is None,
    It allows to receive additional information from a parent resource (using `resource` field)
    based on the request with params (using `child_enum_params` tuples) and map result object
    to the resource (using `parent_get_params` tuples).

Get methods is created based on `get` methods of GCP resources. As a rule the `get` methods
have required fields like project name, ID of loading resource etc. The available fields names
with appropriate information are located in Stackdriver logs.

.. code-block:: python

    from c7n_gcp.provider import resources
    from c7n_gcp.query import QueryResourceManager, TypeInfo


    @resources.register('loadbalancer-address')
    class LoadBalancingAddress(QueryResourceManager):

        class resource_type(TypeInfo):
            service = 'compute'
            component = 'addresses'
            version = 'v1'
            enum_spec = ('aggregatedList', 'items.*.addresses[]', None)
            scope = 'project'
            id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {
                'project': resource_info['project_id'],
                'region': resource_info['location'],
                'address': resource_info[
                    'resourceName'].rsplit('/', 1)[-1]})

Load New GCP Resource
---------------------

Once the required dependecies are installed and created the new GCP Resource, custodian will
load all registered resources. Import the resource in
``entry.py``.

.. code-block:: python

    import c7n_gcp.resources.loadbalancer

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

