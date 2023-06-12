.. _bucketquerystorage:

Bucket - Fetch all the buckets from the specified compartments
==============================================================

To retrieve the buckets from the specified compartments, the `OCI_COMPARTMENTS` environment variable needs to be set with the compartment OCID. Multiple compartment OCID's can be specified as comma separate values. By default, without `OCI_COMPARTMENTS` environment variable, the resources are queried at the tenancy level.

.. code-block:: yaml

    export OCI_COMPARTMENTS=ocid1.test.oc1..<unique_ID>EXAMPLE1-compartmentId-Value,ocid1.test.oc1..<unique_ID>EXAMPLE2-compartmentId-Value

Then the following example policy will retrieve all the buckets from the above mentioned compartments.


.. code-block:: yaml

    policies:
     - name: list-bucket-in-compartments
       description: Lists all the buckets resides in the specified compartments
       resource: oci.bucket

