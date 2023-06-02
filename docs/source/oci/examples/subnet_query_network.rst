.. _subnetquerynetwork:

Subnet - Filter all the subnets from the specified compartments
===============================================================

The following example policy will filter all the subnet from the specified lists of compartments

.. code-block:: yaml

    policies:
    - name: filter-subnet-compartments
      description: |
        Filter all the subnet in the specified compartments
      resource: oci.subnet
      query: [
                'compartment_ids': [
                      'ocid1.test.oc1..<unique_ID>EXAMPLE1-compartmentId-Value',
                      'ocid1.test.oc1..<unique_ID>EXAMPLE2-compartmentId-Value',
                      'ocid1.test.oc1..<unique_ID>EXAMPLE3-compartmentId-Value'
                      ]
                ]
