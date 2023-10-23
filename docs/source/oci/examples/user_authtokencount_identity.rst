.. _userauthtokencountidentity:

User - Filter all the users who have auth tokens
================================================

The following example policy will filter and tag the users who have auth tokens

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-auth-tokens
      description: |
        Filter and tag users who have auth tokens
      resource: oci.user
      filters:
       - type: auth-tokens
         key: auth_tokens
         value_type: size
         op: greater-than
         value: 0
      actions:
       - type: update
         freeform_tags:
           TagName : TagValue
