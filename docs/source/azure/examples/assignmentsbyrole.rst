Filter assignments by role name
===============================

.. code-block:: yaml

    policies:
       - name: assignment-by-role
         resource: azure.roleassignment
         filters:
            - type: role
              key: properties.roleName
              op: eq
              value: Owner