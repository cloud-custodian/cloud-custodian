.. _usersmtpcredinactiveidentity:

User - Filter all the users who have inactive SMTP credentials
==============================================================

The following example policy will filter and tag the users who have inactive SMTP credentials

.. code-block:: yaml

    policies:
    - name: filter-tag-user-with-inactive-smtp-credentials
      description: |
        Filter and tag users with inactive smtp credentials
      resource: oci.user
      filters:
       - type: smtp-credentials
         key: smtp_credential.lifecycle_state
         op: equal
         value: 'INACTIVE'
      actions:
       - type: update
         freeform_tags:
            TagName : TagValue
