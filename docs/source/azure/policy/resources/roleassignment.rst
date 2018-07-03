.. _azure_roleassignment:

App Service Plan
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `RoleAssignment <https://docs.microsoft.com/en-us/python/api/azure.mgmt.authorization.models.roleassignment?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
- ``role``
  Filters role assignments based on role definitions
  .. c7n-schema:: UserRole
      :module: c7n_azure.resources.access_control

Actions
-------

- ARM Resource Actions (see :ref:`azure_genericarmaction`)
