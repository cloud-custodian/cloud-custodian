.. _vcnfilternetwork:

VCN - Filter all the VCN based on the tags
==========================================

The following example policy will filter all the VCN in the tenancy based on the specified tags

.. code-block:: yaml

    policies:
    - name: filter-vcn
      description: |
        Filter all the VCN in the tenancy based on the tags
      resource: oci.vcn
      filters:
       - type: value
         key: 'freeform_tags.TagName'
         value: TagValue
         op: eq
