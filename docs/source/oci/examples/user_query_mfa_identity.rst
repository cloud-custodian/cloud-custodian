.. _userquerymfaidentity:

User - Filter all the users whose MFA is not enabled
====================================================

The following example policy will filter and tag the users whose multi-factor authentication is not enabled

.. code-block:: yaml

    policies:
    - name: filter-tag-user-without-mfa
      description: |
        Filter and tag users whose MFA is not enabled
      resource: oci.user
      filters:
       - type: attributes
         key: is_mfa_activated
         value: false
      actions:
       - type: update
         freeform_tags:
            'mfa_activated' : 'false'
