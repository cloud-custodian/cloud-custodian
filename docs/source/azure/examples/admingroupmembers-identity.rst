Entra ID - Administrative Group Members
=======================================

Find users who are members of administrative groups such as Global Administrators, Privileged Role Administrator, and User Admin.

.. code-block:: yaml

    policies:
      - name: global-admin-members
        resource: azure.entraid-user
        description: |
          Find users who are members of administrative groups.
          This policy helps identify users with elevated privileges.
          Note: Requires GroupMember.Read.All permission.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: group-membership
            groups:
              - 'Global Administrators'
              - 'Privileged Role Administrator'
              - 'User Admin'
            match: any

Find administrative group members without multi-factor authentication enabled.

.. code-block:: yaml

    policies:
      - name: admin-group-members-without-mfa
        resource: azure.entraid-user
        description: |
          Find administrative group members without MFA.
          Critical security finding - admin users should always have MFA.
          Note: Requires GroupMember.Read.All and UserAuthenticationMethod.Read.All permissions.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: group-membership
            groups:
              - 'Global Administrators'
              - 'Privileged Role Administrator'
              - 'Security Administrator'
              - 'User Administrator'
            match: any
          - type: mfa-enabled
            value: false
