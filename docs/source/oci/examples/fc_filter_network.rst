.. _fcfilternetwork:

Fast Connect - Filter all the fast connect based on a tag
=========================================================

The following example policy will filter all the fast connect in the tenancy based on a specified tag

.. code-block:: yaml

    policies:
    - name: filter-fast-connect
      description: |
        Filter all the fast connect in the tenancy based on a tag
      resource: oci.cross_connect
      filters:
       - type: value
         key: 'freeform_tags.cloud_custodian'
         value: 'true'
         op: eq
