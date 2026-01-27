.. _userdbcredentialscountidentity:

User - Filter all the users who have DB credentials
=====================================================

The following example policy will filter and tag the users who have DB credentials

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-db-credentials
      description: |
        Filter and tag users with DB credentials
      resource: oci.user
      filters:
       - type: db-credentials
         key: db_credentials
         value_type: size
         op: greater-than
         value: 0
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
