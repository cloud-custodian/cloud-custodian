Entra ID - Users by Department
==============================

Find users in the IT department by filtering on the department field.

.. code-block:: yaml

    policies:
      - name: it-department-users
        resource: azure.entraid-user
        description: |
          Find users in the IT department.
          This policy demonstrates filtering by department field.
          Modify the department value to match your organization's structure.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: value
            key: department
            value: IT
