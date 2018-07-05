.. _azure_roledefinition:

App Service Plan
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `RoleAssignment <https://docs.microsoft.com/en-us/python/api/azure.mgmt.authorization.models.roledefinition?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will find all Owner role assignments and notify user@domain.com

.. code-block:: yaml

     policies:
       - name: assignments-by-role-definition
         resource: azure.roleassignment
         filters:
            - type: role
              key: properties.roleName
              op: in
              value: Owner
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Owners on Azure Subscription
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
