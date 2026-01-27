.. _userapikeycountidentity:

User - Filter all the users with API Keys
=========================================

The following example policy will filter and tag the users with the API keys count more than 2

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-api-keys
      description: |
        Filter and tag users with more than 2 API keys
      resource: oci.user
      filters:
       - type: api-keys
         key: api_keys
         value_type: size
         op: greater-than
         value: 2
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
