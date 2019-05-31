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

This policy will find all CosmosDB with 1000 or less total requests over the last 72 hours

.. code-block:: yaml

    policies:
      - name: cosmosdb-inactive
        resource: azure.cosmosdb
        filters:
          - type: metric
            metric: TotalRequests
            op: le
            aggregation: total
            threshold: 1000
            timeframe: 72
