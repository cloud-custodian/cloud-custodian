.. _instancetagcompute:

Instance - Query and tag all the instances in the compartment
=============================================================

The following example policy lists all the instances in the specified compartment and adds defined tag to the instances


.. code-block:: yaml

    policies:
     - name: list-tag-instances-in-compartment
       description: |
         Lists and tag all the instances in the compartment
       resource: oci.instance
       query: [
          'compartment_id': 'ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value'
          ]
       actions:
        - type: update_instance
          params:
           update_instance_details:
             defined_tags:
                cloud_custodian:
                    'environment': 'dev'
