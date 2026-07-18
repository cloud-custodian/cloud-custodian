Entra ID - Enabled Member Users
===============================

Find users who are both enabled and classified as internal member users.

.. code-block:: yaml

    policies:
      - name: enabled-member-users
        resource: azure.entraid-user
        description: |
          Find users who are both enabled AND internal members.
          This policy demonstrates multiple filter conditions (AND logic).
          Useful for identifying active internal users.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: value
            key: userType
            value: Member
