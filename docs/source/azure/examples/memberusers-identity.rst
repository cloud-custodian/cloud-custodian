Entra ID - Member Users
=======================

Find all users classified as internal member users.

.. code-block:: yaml

    policies:
      - name: member-users
        resource: azure.entraid-user
        description: |
          Find all member users (internal users) in the directory.
          This policy helps distinguish between internal and external users.
        filters:
          - type: value
            key: userType
            value: Member
