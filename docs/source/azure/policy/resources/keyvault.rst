.. _azure_keyvault:

Key Vault
=========

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Vault <https://docs.microsoft.com/en-us/python/api/azure.mgmt.keyvault.models.vault?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Key Vault Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftkeyvaultvaults/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all Key Vaults for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-keyvaults-for-deletion
        resource: azure.keyvault
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
      - name: delete-test-keyvaults
        resource: azure.keyvault
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all KeyVaults with 10 or less API Hits over the last 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-inactive-keyvaults
        resource: azure.keyvault
        filters:
          - type: metric
            metric: ServiceApiHit
            op: ge
            aggregation: total
            threshold: 10
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Inactive Key Vault
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
