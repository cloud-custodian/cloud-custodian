.. _userstaleoauthcredidentity:

User - Filter all the users with stale OAuth credentials
========================================================

The following example policy will filter and tag the users who have stale OAuth credentials

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-stale-oauth-credentials
      description: |
        Filter and tag users who have stale OAuth credentials
      resource: oci.user
      filters:
        - or:
          - type: o-auth2-client-credentials
            key: o_auth2_client_credential.lifecycle_state
            op: equal
            value: 'INACTIVE'
          - type: o-auth2-client-credentials
            key: o_auth2_client_credential.time_expires
            value_type: expiration
            op: greater-than
            value: 0
      actions:
        - type: update
          freeform_tags:
             TagName : TagValue
