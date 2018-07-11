.. _azure_cosmosdb:

Cosmos DB
=========

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `DatabaseAccount <https://docs.microsoft.com/en-us/python/api/azure.mgmt.cosmosdb.models.databaseaccount?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Cosmos DB Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdocumentdbdatabaseaccounts/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all CosmosDB for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-cosmosdb-for-deletion
        resource: azure.cosmosdb
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
      - name: delete-marked-cosmosdbs
        resource: azure.cosmosdb
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all CosmosDB with 1000 or less total requests over the last 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-cosmosdb-inactive
        resource: azure.cosmosdb
        filters:
          - type: metric
            metric: TotalRequests
            op: le
            aggregation: total
            threshold: 1000
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Inactive CosmosDB
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
