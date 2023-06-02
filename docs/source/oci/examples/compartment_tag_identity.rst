.. _compartmenttagidentity:

Compartment - Tag all the compartments
======================================

The following example policy will tag all the child compartments under the specified compartment with a
specified freeform tag

.. code-block:: yaml

    policies:
      - name: filter-and-add-tag-on-child-compartment
        description: Filter and add tag on the child compartment
        resource: oci.compartment
        query: [
          'compartment_ids': [
                        'ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value'
                    ]
          ]
        actions:
          - type: update-compartment
            params:
              update_compartment_details:
                freeform_tags:
                  "custodian_development": 'true'
