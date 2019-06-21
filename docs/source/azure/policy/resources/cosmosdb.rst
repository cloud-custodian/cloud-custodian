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
    
- ``firewall-rules`` Firewall Rules Filter
    Filter based on firewall rules. Rules can be specified as x.x.x.x-y.y.y.y or x.x.x.x or x.x.x.x/y.

    - `include`: the list of IP ranges or CIDR that firewall rules must include. The list must be a subset of the exact rules as is, the ranges will not be combined.
    - `equal`: the list of IP ranges or CIDR that firewall rules must match exactly.

  .. c7n-schema:: azure.storage.filters.firewall-rules

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
