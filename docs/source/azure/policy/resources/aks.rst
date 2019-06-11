.. _azure_aks:

Azure Kubernetes Service
========================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `ContainerService <https://docs.microsoft.com/en-us/python/api/azure-mgmt-containerservice/azure.mgmt.containerservice.models.containerservice?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

Returns all aks clusters that did not provision successfully

.. code-block:: yaml

    policies:
      - name: broken-aks
        resource: azure.aks
        filters:
          - type: value
            key: properties.provisioningState
            op: not-equal
            value_type: normalize
            value: succeeded
