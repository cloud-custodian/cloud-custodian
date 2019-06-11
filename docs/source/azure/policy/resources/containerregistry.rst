.. _azure_containerregistry:

Container Registry
==================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `OperationDefinition <https://docs.microsoft.com/en-us/python/api/azure-mgmt-containerregistry/azure.mgmt.containerregistry.v2017_10_01.models.operationdefinition?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

Returns all container registry named my-test-container-registry

.. code-block:: yaml

    policies:
    - name: get-container-registry
      resource: azure.containerregistry
      filters:
        - type: value
          key: name
          op: eq
          value: my-test-container-registry
