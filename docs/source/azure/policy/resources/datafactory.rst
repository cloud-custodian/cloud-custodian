.. _azure_datafactory:

Data Factory
============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Vault <https://docs.microsoft.com/en-us/python/api/azure.mgmt.keyvault.models.vault?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Data Factory Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdatafactoryfactories/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all Data Factories for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-datafactories-for-deletion
        resource: azure.datafactory
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
      - name: delete-test-datafactories
        resource: azure.datafactory
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all Data Factories with 10 or more failures in pipeline runs over the last 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-datafactory-dropping-messages
        resource: azure.datafactory
        filters:
          - type: metric
            metric: PipelineFailedRuns
            op: ge
            aggregation: total
            threshold: 10
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Datafactory Pipeline Failing
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
