.. _usersmtpcredcountidentity:

User - Filter all the users who have SMTP credentials
=====================================================

The following example policy will filter and tag the users who have SMTP credentials

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-smtp-credentials
      description: |
        Filter and tag users with smtp credentials
      resource: oci.user
      filters:
       - type: smtp-credentials
         key: smtp_credentials
         value_type: size
         op: greater-than
         value: 0
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
