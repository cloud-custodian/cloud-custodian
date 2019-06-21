.. _azure_resourcegroup:

Resource Groups
===============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `ResourceGroup <https://docs.microsoft.com/en-us/python/api/azure.mgmt.resource.resources.v2017_05_10.models.resourcegroup?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource
- ``empty-group``
  Filter based on empty resource groups

  .. c7n-schema:: azure.resourcegroup.filters.empty-group


Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)
- ``delete``
  Delete a resource group

  .. c7n-schema:: azure.resourcegroup.actions.delete



Example Policies
----------------

This policy will delete all empty resource groups

.. code-block:: yaml

     policies:
       - name: delete-empty-groups
         resource: azure.resourcegroup
         filters:
          - type: empty-group
         actions:
          - type: delete
