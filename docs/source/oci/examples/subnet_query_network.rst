.. _subnetquerynetwork:

Subnet - Filter all the subnets from the specified compartments
===============================================================

Set the `OCI_COMPARTMENTS` environment variable with the compartment OCID's like below. Multiple compartments can be separated by comma. By default, without `OCI_COMPARTMENTS` environment variable, the resources are queried at the tenancy level.

.. code-block:: yaml

    export OCI_COMPARTMENTS=ocid1.test.oc1..<unique_ID>EXAMPLE1-compartmentId-Value,ocid1.test.oc1..<unique_ID>EXAMPLE2-compartmentId-Value

The following example policy will filter all the subnet from the specified lists of compartments

.. code-block:: yaml

    policies:
    - name: filter-subnet-compartments
      description: |
        Filter all the subnet in the specified compartments
      resource: oci.subnet
