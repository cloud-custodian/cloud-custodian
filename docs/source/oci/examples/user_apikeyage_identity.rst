.. _userapikeyageidentity:

User - Filter all the users with key api key age greater than one year
======================================================================

The following example policy will filter and tag the users whose API keys age is greater than 365 days

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-api-key-age
      description: |
        Filter and tag users whose api key age is greater than one year
      resource: oci.user
      filters:
       - type: api-keys
         key: api_key.time_created
         op: greater-than
         value_type: age
         value: 365
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
