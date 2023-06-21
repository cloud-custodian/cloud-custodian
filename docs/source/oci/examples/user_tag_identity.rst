.. _usertagidentity:

User - Tag all the users
========================

The following example policy will tag all the users in the tenancy

.. code-block:: yaml

    policies:
    - name: tag-user
      description: |
        Tag all the users in the tenancy
      resource: oci.user
      actions:
       - type: update-user
         params:
          update_user_details:
            freeform_tags:
                TagName : TagValue
