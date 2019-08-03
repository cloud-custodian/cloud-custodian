.. _azure_apimanagement:

API Management
==============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `API Management <https://github.com/Azure/azure-sdk-for-python/blob/master/sdk/apimanagement/azure-mgmt-apimanagement/azure/mgmt/apimanagement/models/api_management_service_resource.py>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

Returns all API management resources

.. code-block:: yaml

    policies:
      - name: all-api-management-resources
        resource: azure.api-management
