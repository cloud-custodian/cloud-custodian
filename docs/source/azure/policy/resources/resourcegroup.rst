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

  .. c7n-schema:: EmptyGroup
      :module: c7n_azure.resources.resourcegroup

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)
- ``delete``
  Delete a resource group

  .. c7n-schema:: DeleteResourceGroup
      :module: c7n_azure.resources.resourcegroup


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

This set of policies will mark all resource groups for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-groups-for-deletion
        resource: azure.resourcegroup
        filters:
          - type: value
            key: name
            op: in
            value_type: normalize
            value: test
         actions:
          - type: mark-for-op
            op: delete
            days: 7
      - name: delete-test-resource-groups
        resource: azure.resourcegroup
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete
