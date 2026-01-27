.. _oci_gettingstarted:

Getting Started (Beta)
=======================

The Oracle Cloud Infrastructure (OCI) provider (Beta) is an optional package. which can be installed to enable
writing policies which interact with OCI related resources.



.. _oci_install-custodian:

Install the OCI plugin
-----------------------

First, ensure you have :ref:`installed the base Cloud Custodian application
<install-cc>`. Cloud Custodian is a Python application and must run on an
`actively supported <https://devguide.python.org/#status-of-python-branches>`_
version.

Once the base install is complete, you are now ready to install the OCI provider package
using one of the following options:

Option 1: Install released packages to local Python Environment
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    pip install c7n
    pip install c7n-oci


Option 2: Install latest from the repository
"""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    git clone https://github.com/cloud-custodian/cloud-custodian.git
    pip install -e ./cloud-custodian
    pip install -e ./cloud-custodian/tools/c7n_oci

.. _oci_authenticate:

Authentication
--------------

In order for Cloud Custodian to be able to interact with your OCI resources, you will need to
configure your OCI authentication credentials on your system.

The OCI CLI setup can be used to configure the authentication. Other approaches are documented here -
`Authentication <https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm>`_

OCI CLI
"""""""

First, `install OCI CLI <https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm>`_

Then run the following command:

.. code-block:: bash

    oci setup config

After the configuration is complete, Cloud Custodian will implicitly pick up your credentials when it runs.


Instance Principal Authentication
"""""""""""""""""""""""""""""""""

Cloud custodian can also be run on an OCI instance to make use of instance principal auth.
To enable authentication using instance principal, set the environment variable ``OCI_CLI_AUTH`` to ``instance_principal``.
For e.g.

.. code-block:: bash

    export OCI_CLI_AUTH=instance_principal


For more details on how to use instance principal auth please click `here <https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm>`_.

.. _oci_run-policy:

Run your first policies
-----------------------

Example 1
"""""""""

Our first policy filters compute instance of a specific name, then adds the tag ``mark_deletion: true``.

Create a file named ``custodian.yml`` with the following content. Update ``display_name`` to match an existing compute instance.

.. code-block:: yaml

    policies:
      - name: filter-for-compute-name
        description: Filter for compute which matches the  name
        resource: oci.instance
        filters:
          - type: value
            key: display_name
            value: test
        actions:
          - type: update
            freeform_tags:
              mark-for-deletion: 'true'


Run the following from the command line:

.. code-block:: bash

    custodian run --output-dir=. custodian.yml

If successful, you should see output like the following on the command line::

    2023-05-25 18:15:53,132: custodian.oci.session:INFO Successfully authenticated user ...
    2023-05-25 18:15:59,178: custodian.oci.query:INFO custodian.oci.query:INFO List of compartment IDs fetched using the ResourceSearchClient: {'ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-1-Value', 'ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-3-Value'}
    2023-05-25 18:16:01,118: custodian.policy:INFO policy:filter-for-compute-name resource:oci.instance region: count:1 time:7.98
    2023-05-25 18:16:05,474: custodian.oci.resources.compute:INFO Received status 200 for PUT:update_instance 9A14E2D68AC94772849C75E10BC963/089249DEBA83A0BDA50BFF759BCF49/38040CF37F35674339E653B2DED1E0
    2023-05-25 18:16:05,483: custodian.policy:INFO policy:filter-for-compute-name action:updateinstance resources:1 execution_time:4.34


Under the ‘output-dir’ a new directory with the name of the policy will be created which will contain a log and json files describing the resources

By default the filter will be run for all compartments in the tenancy that contain the type of resources specified in the policy.
You can override this behavior by specifying one of more compartment ids in the
OCI_COMPARTMENTS environment variable using a comma separated list.

| For example:

.. code-block:: bash

    export OCI_COMPARTMENTS=ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-2-Value,ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-3-Value

Example 2
"""""""""

Our second policy filters running compute instances from a specific compartment and of a specific shape, then adds the tag ``eligible_for_resize: true``.

Create a file named ``custodian_compute.yml`` with the following content.
Update ``compute_shape`` and set  ``OCI_COMPARTMENTS`` environment variable to match an existing compute instance's shape and compartment.

.. code-block:: yaml

    policies:
      - name: scan-for-eligible-VMS
        description: Scan for all the VM's with standard shape
        resource: oci.instance
        query: [
          'lifecycle_state': 'RUNNING'
        ]
        filters:
          - type: value
            key: shape
            value: VM.Standard2.4
        actions:
          - type: update
            freeform_tags:
              eligible_for_resize: 'true'

Run the following from the command line:


.. code-block:: bash

    custodian run --output-dir=. custodian_compute.yml

If successful, you should see output like the following on the command line::

    2023-05-25 17:37:29,266: custodian.oci.session:INFO Successfully authenticated user....
    2023-05-25 17:37:31,178: custodian.oci.query:INFO List of compartment IDs fetched using the environment variable $OCI_COMPARTMENTS: ['ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-1-Value']
    2023-05-25 17:37:34,081: custodian.policy:INFO policy:scan-for-eligible-VMS resource:oci.instance region: count:1 time:4.81
    2023-05-25 17:37:40,017: custodian.oci.resources.compute:INFO Received status 200 for PUT:update_instance BC73BEB7054628AE3EF32E6A2B2A21/AD767EBA6342A2E333115D0BF5779C/FD20E19F47557E5A54D97E361615B7
    2023-05-25 17:37:40,019: custodian.policy:INFO policy:scan-for-eligible-VMS action:updateinstance resources:1 execution_time:5.94




