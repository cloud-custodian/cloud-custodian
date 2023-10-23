.. _compartmenttagidentity:

Compartment - Tag all the child compartments
============================================

Set the `OCI_COMPARTMENTS` environment variable with the parent compartment OCID like below.

.. code-block:: yaml

    export OCI_COMPARTMENTS=ocid1.test.oc1..<unique_ID>EXAMPLE1-compartmentId-Value

The following example policy will tag all the child compartments under the specified parent compartment with a specified freeform tag

.. code-block:: yaml

    policies:
      - name: filter-and-add-tag-on-child-compartment
        description: Filter and add tag on the child compartments
        resource: oci.compartment
        actions:
          - type: update
            freeform_tags:
               "custodian_development": 'true'
