.. _azure_roledefinition:

App Service Plan
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `RoleAssignment <https://docs.microsoft.com/en-us/python/api/azure.mgmt.authorization.models.roledefinition?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will find all Owner role assignments

.. code-block:: yaml

     policies:
       - name: assignments-by-role-definition
         resource: azure.roleassignment
         filters:
            - type: role
              key: properties.roleName
              op: in
              value: Owner
