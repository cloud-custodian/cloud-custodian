Entra ID - Users with MFA
=========================

Find users who have multi-factor authentication (MFA) enabled.

.. code-block:: yaml

    policies:
      - name: users-with-mfa
        resource: azure.entraid-user
        description: |
          Find users who have multi-factor authentication enabled.
          This policy helps identify users with proper security measures in place.
          Note: Requires UserAuthenticationMethod.Read.All permission.
        filters:
          - type: mfa-enabled
            value: true
