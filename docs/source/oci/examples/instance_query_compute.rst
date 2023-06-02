.. _instanceinstancecompute:

Instance - Querying the instances from the lists of compartment
===============================================================

The following example policy lists all the instances in the specified lists of compartments


.. code-block:: yaml

    policies:
     - name: list-instances-from-compartments
       description: |
         Lists all the instances in the specified compartments
       resource: oci.instance
       query: [
          'compartment_ids': [
                'ocid1.test.oc1..<unique_ID>EXAMPLE1-compartmentId-Value',
                'ocid1.test.oc1..<unique_ID>EXAMPLE2-compartmentId-Value',
                'ocid1.test.oc1..<unique_ID>EXAMPLE3-compartmentId-Value'
                ]
          ]