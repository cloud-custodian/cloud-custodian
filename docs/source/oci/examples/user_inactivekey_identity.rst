.. _userinactivekeyidentity:

User - Filter all the users with INACTIVE API Keys
==================================================

The following example policy will filter and tag the users with the INACTIVE API keys

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-inactive-api-keys
      description: |
        Filter and tag users with inactive api keys
      resource: oci.user
      filters:
       - type: api-keys
         key: api_key.lifecycle_state
         op: equal
         value: 'INACTIVE'
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
