Entra ID - Disabled Users
=========================

Find all user accounts that have been disabled.

.. code-block:: yaml

    policies:
      - name: disabled-users
        resource: azure.entraid-user
        description: |
          Find all disabled user accounts in the directory.
          This policy helps identify inactive accounts that may need cleanup.
        filters:
          - type: value
            key: accountEnabled
            value: false
