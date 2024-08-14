.. _userstaleauthtokenidentity:

User - Filter all the users with stale auth tokens
==================================================

The following example policy will filter and tag the users who have stale auth tokens

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-stale-auth-tokens
      description: |
        Filter and tag users who have stale auth tokens
      resource: oci.user
      filters:
        - or:
          - type: auth-tokens
            key: auth_token.lifecycle_state
            op: equal
            value: 'INACTIVE'
          - type: auth-tokens
            key: auth_token.time_expires
            value_type: expiration
            op: greater-than
            value: 0
      actions:
        - type: update
          freeform_tags:
             TagName : TagValue
