.. _useroauthcredcountidentity:

User - Filter all the users who have OAuth credentials
======================================================

The following example policy will filter and tag the users who have OAuth credentials

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-oauth-credentials
      description: |
        Filter and tag users with OAuth credentials
      resource: oci.user
      filters:
       - type: o-auth2-client-credentials
         key: o_auth2_client_credentials
         value_type: size
         op: greater-than
         value: 0
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
