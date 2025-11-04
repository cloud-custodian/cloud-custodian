Entra ID - Enabled Users
========================

Find all user accounts that are currently enabled.

.. code-block:: yaml

    policies:
      - name: enabled-users
        resource: azure.entraid-user
        description: |
          Find all enabled user accounts in the directory.
          This policy helps identify active user accounts for auditing purposes.
        filters:
          - type: value
            key: accountEnabled
            value: true
