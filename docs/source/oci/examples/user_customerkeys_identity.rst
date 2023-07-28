.. _usercustomerkeyscountidentity:

User - Filter all the users with Customer Secret Keys
=====================================================

The following example policy will filter and tag the users with the Customer secret keys

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-secret-keys
      description: |
        Filter and tag users with customer secret keys
      resource: oci.user
      filters:
       - type: customer-secret-keys
         key: customer_secret_keys
         value_type: size
         op: greater-than
         value: 0
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
