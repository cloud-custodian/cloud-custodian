.. _subnetfilternetwork:

Subnet - Filter all the subnet based on a tag
=============================================

The following example policy will filter all the subnet in the tenancy based on a specified tag

.. code-block:: yaml

    policies:
    - name: filter-subnet
      description: |
        Filter all the subnet in the tenancy based on a tag
      resource: oci.subnet
      filters:
       - type: value
         key: 'freeform_tags.TagName'
         value: TagValue
         op: eq
