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

    import c7n_gcp.resources.<name of a file with created resources>

Each resource has to have test cases. There are implemented test cases for resources list methods and get methods.

Test cases for resources list methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To create a test case for `list` method is used following scenario.

- A factory is created based on recording real data from a GCP project resource.

    .. code-block:: python

        factory = self.record_flight_data(<name of a file>, project_id=project_id)

The `name of a file` means the folder name that has JSON file(s) with expected response(s) on the request from a testing policy.

- The factory is used for creating the testing policy.

    .. code-block:: python

        policy = self.load_policy(
            {'name': '<policy name>',
             'resource': 'gcp.<name of the resource>'},
            session_factory=factory)

The `policy name` means the name of the policy. It can be used any name of the policy.
The `name of the resource` is the name of testing resource. It's the resource_name from @resources.register('<resource_name>').

- The result of the running policy is a list of resources. Below code can be used for the policy running:

    .. code-block:: python

        resources = policy.run()

- The next step is current results verification with expecting results.

- Last step is replacing `record_flight_data` in creating the factory by `replay_flight_data`. After that step recorded data in JSON files will be used instead of real data. Name of project in GOOGLE_CLOUD_PROJECT may be replaced on any one.


Test cases for resources get methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To create a test case for `get` method is used following scenario.

- A factory was created based on recording real data from a GCP project resource.

    .. code-block:: python

        factory = self.record_flight_data(<name of a file>, project_id=project_id)

The `name of a file` means the folder name that has JSON file(s) with expected response(s) on the request from a testing policy.

- The factory is used for creating the testing policy.

    .. code-block:: python

        policy = self.load_policy(
            {'name': '<policy name>',
             'resource': 'gcp.<name of the resource>',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': []
             }},
            session_factory=factory)

The `policy name` means the name of the policy. It can be used any name of the policy.
The `name of the resource` is the name of testing resource. It's the resource_name from @resources.register('<resource_name>').
The policy should be tested in gcp-audit mode.

- The next step is invoking `get` method of GCP resource that is used for development. The result of invoking is logged in Stackdriver. The result should be copied from Stackdriver log and be put into a JSON file in tools/c7n_gcp/test/data/events folder.

- The next step is creating an event based on JSON file that was created in the previous step. The event is run within policy's execution mode. The sample is below.

    .. code-block:: python

        exec_mode = policy.get_execution_mode()
        event = event_data('<name of JSON file>')
        instances = exec_mode.run(event, None)

- Further current results should be verified with expecting results.

- Last step is replacing `record_flight_data` in creating the factory by `replay_flight_data`. After that step recorded data in JSON files will be used instead of real data. Name of project in GOOGLE_CLOUD_PROJECT may be replaced on any one.

Testing
========

Tests for c7n_gcp run automatically with other Custodian tests. See :ref:`Testing for Developers <developer-tests>` for information on how to run Tox.

If you'd like to run tests at the command line or in your IDE then reference `tox.ini` to see the required
environment variables and command lines for running `pytest`.

Running tests
---------------

You can use `tox` to run all tests or instead you can use `pytest` and run only GCP tests (or only specific set of tests). Running recorded tests still requires some authentication, it is possible to use fake data for credentials to GCP and name of Google Cloud project.

.. code-block:: bash

  export GOOGLE_CLOUD_PROJECT=cloud-custodian
  export GOOGLE_APPLICATION_CREDENTIALS=data/credentials.json
  pytest tools/c7n_gcp/tests
