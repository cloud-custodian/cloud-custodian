.. _userdbcredentialsageidentity:

User - Filter all the users whose DB credentials age greater than 3 months
==========================================================================

The following example policy will filter and tag the users who have DB credentials with age greater than 90 days

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-db-credentials-age
      description: |
        Filter and tag users with DB credentials whose age is greater than 3 months
      resource: oci.user
      filters:
       - type: db-credentials
         key: db_credential.time_created
         value_type: age
         op: greater-than
         value: 90
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
