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

This set of policies will find all Azure Batch services that have more than 100 cores as the limit for the dedicated core quota.

.. code-block:: yaml

    policies:
      - name: find-batch-with-high-dedicated-cores
        resource: azure.batch
      resource: azure.batch
      filters:
        - type: value
          key: properties.dedicatedCoreQuota
          op: gt
          value: 100