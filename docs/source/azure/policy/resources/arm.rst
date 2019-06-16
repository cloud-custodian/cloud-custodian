.. _azure_armresource:

Azure ARM Resource
==================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `GenericResource <https://docs.microsoft.com/en-us/python/api/azure.mgmt.resource.resources.v2017_05_10.models.genericresource?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource
- ``resource-type`` filter
    - Filter on ARM resource types, including resource type namespaces
    - Provide a list of resource types (case-insensitive) in a ``values`` array

    .. c7n-schema:: azure.armresource.filters.resource-type


Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

