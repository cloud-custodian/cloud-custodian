.. _fctagnetwork:

Fast connect - Tag all the fast connect in the tenancy
======================================================

The following example policy will tag all the fast connect in the tenancy

.. code-block:: yaml

    policies:
    - name: tag-fast-connect
      description: |
        Tag all the fast connect in the tenancy
      resource: oci.cross_connect
      actions:
       - type: update-cross-connect
         params:
           update_cross_connect_details:
             freeform_tags:
               TagName: TagValue
