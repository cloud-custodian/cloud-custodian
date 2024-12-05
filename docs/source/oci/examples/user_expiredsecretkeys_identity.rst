.. _userexpiredcustomerkeysidentity:

User - Filter all the users with expired Customer Secret Keys
=============================================================

The following example policy will filter and tag the users with the expired customer secret keys

.. code-block:: yaml

    policies:
    - name: filter-tag-users-with-expired-customer-secret-keys
      description: |
        Filter and tag users with expired customer secret keys
      resource: oci.user
      filters:
       - type: customer-secret-keys
         key: customer_secret_key.time_expires
         value_type: age
         op: greater-than
         value: 0
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
