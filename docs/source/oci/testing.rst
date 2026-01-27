Testing
=========

Tests for c7n_oci run automatically with other Cloud Custodian tests.  See :ref:`Testing for Developers <developer-tests>`.

Running Tests
~~~~~~~~~~~~~

You can use ``make test`` to run all tests or instead you can use ``pytest`` and run only Oracle Cloud Infrastructure (OCI) tests.


Functional (live) Tests
~~~~~~~~~~~~~~~~~~~~~~~

Functional tests run against OCI using your tenancy. In order to execute live tests you will need to set below additional environment variables before invoking the test.

For example:

.. code-block:: bash

   export TF_VAR_OCI_TENANCY_ID=ocid1.tenancy.oc1..<unique_ID>
   export TF_VAR_OCI_COMPARTMENT_ID=ocid1.compartment.oc1..<unique_ID>
   export TF_VAR_OCI_COMPUTE_IMAGE_ID=ocid1.image.oc1.iad.<unique_ID>
   export C7N_FUNCTIONAL=yes
   pytest -n auto -s tools/c7n_oci

Unit Tests
~~~~~~~~~~
Unit tests run against previously recorded query/response data.
Though the unit tests do not access OCI, an authorization token and subscription id still need to be in place.
Well-formed mock values can be used.

Run the unit tests as follow:

.. code-block:: bash

    export C7N_FUNCTIONAL=no
    pytest -n auto -s tools/c7n_oci
