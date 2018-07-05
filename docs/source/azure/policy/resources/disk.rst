.. _azure_disk:

Key Vault
=========

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Vault <https://docs.microsoft.com/en-us/python/api/azure.mgmt.keyvault.models.vault?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all IoT Hubs for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-iothubs-for-deletion
        resource: azure.iothub
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
      - name: delete-test-iothubs
        resource: azure.iothub
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete
