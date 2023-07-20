.. _instancetagcompute:

Instance - Query and tag all the instances in the compartment
=============================================================

Set the `OCI_COMPARTMENTS` environment variable with the compartment OCID's like below. Multiple compartments can be separated by comma. By default, without `OCI_COMPARTMENTS` environment variable, the resources are queried at the tenancy level.

.. code-block:: yaml

    export OCI_COMPARTMENTS=ocid1.test.oc1..<unique_ID>EXAMPLE1-compartmentId-Value,ocid1.test.oc1..<unique_ID>EXAMPLE2-compartmentId-Value

The following example policy lists all the instances in the specified compartment and adds defined tag to the instances


.. code-block:: yaml

    policies:
     - name: list-tag-instances-in-compartment
       description: |
         Lists and tag all the instances in the compartment
       resource: oci.instance
       actions:
        - type: update
          defined_tags:
             cloud_custodian:
                'environment': 'dev'
