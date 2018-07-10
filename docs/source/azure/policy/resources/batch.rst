.. _azure_batch:

Batch
=====

Filters
--------
- Standard Value Filter (see :ref:`filters`)
    - Model: `BatchAccount <https://docs.microsoft.com/en-us/python/api/azure.mgmt.batch.models.batchaccount?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all Batch Accounts for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-batch-for-deletion
        resource: azure.batch
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
      - name: delete-test-batch
        resource: azure.batch
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete