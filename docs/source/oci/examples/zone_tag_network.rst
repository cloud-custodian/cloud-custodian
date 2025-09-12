.. _zonetagnetwork:

Zone - Tag all the zones in the tenancy
=======================================

The following example policy will tag all the zones in the tenancy

.. code-block:: yaml

    policies:
    - name: tag-zone
      description: |
        Tag all the zones in the tenancy
      resource: oci.zone
      actions:
       - type: update
         freeform_tags:
            TagName: TagValue
