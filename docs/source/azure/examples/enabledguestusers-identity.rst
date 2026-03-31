Entra ID - Enabled Guest Users
==============================

Find users who are both enabled and classified as guest users.

.. code-block:: yaml

    policies:
      - name: enabled-guest-users
        resource: azure.entraid-user
        description: |
          Find users who are both enabled AND guest users.
          This policy demonstrates multiple filter conditions (AND logic).
          This typically returns fewer results since most guests are managed differently.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: value
            key: userType
            value: Guest
