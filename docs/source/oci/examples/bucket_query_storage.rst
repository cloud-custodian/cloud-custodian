.. _bucketquerystorage:

Bucket - Fetch all the buckets fro the specified compartments
=============================================================

The following example policy will retrieve all the buckets from the specified lists of compartments


.. code-block:: yaml

    policies:
     - name: list-bucket-in-compartments
       description: Lists all the buckets resides in the specified compartments
       resource: oci.bucket
       query: [
          'compartment_ids': [
                'ocid1.test.oc1..<unique_ID>EXAMPLE1-compartmentId-Value',
                'ocid1.test.oc1..<unique_ID>EXAMPLE2-compartmentId-Value',
                'ocid1.test.oc1..<unique_ID>EXAMPLE3-compartmentId-Value'
                ]
          ]
