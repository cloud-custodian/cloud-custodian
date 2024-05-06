.. _grouptagidentity:

Group - Tag all the groups
==========================

The following example policy will tag all the groups in the tenancy

.. code-block:: yaml

    policies:
    - name: tag-group
      description: |
        Tag all the groups in the tenancy
      resource: oci.group
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
