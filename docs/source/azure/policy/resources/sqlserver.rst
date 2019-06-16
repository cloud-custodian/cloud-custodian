.. _azure_sqlserver:

SQL Server
==========

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Server <https://docs.microsoft.com/en-us/python/api/azure.mgmt.sql.models.server?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `SQL Server Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftsqlservers/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

- ``firewall-rules`` Firewall Rules Filter
    Filter based on firewall rules. Rules can be specified as x.x.x.x-y.y.y.y or x.x.x.x or x.x.x.x/y.

    - `include`: the list of IP ranges or CIDR that firewall rules must include. The list must be a subset of the exact rules as is, the ranges will not be combined.
    - `equal`: the list of IP ranges or CIDR that firewall rules must match exactly.

    .. c7n-schema:: azure.sqlserver.filters.firewall-rules


Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------
This policy will find all SQL servers with average DTU consumption under 10 percent over the last 72 hours

.. code-block:: yaml

    policies:
      - name: sqlserver-under-utilized
        resource: azure.sqlserver
        filters:
          - type: metric
            metric: dtu_consumption_percent
            op: lt
            aggregation: average
            threshold: 10
            timeframe: 72
            filter: "ElasticPoolResourceId eq '*'"
            no_data_action: include

This policy will find all SQL servers without any firewall rules defined.

.. code-block:: yaml

    policies:
      - name: find-sqlserver-without-firewall-rules
        resource: azure.sqlserver
        filters:
          - type: firewall-rules
            equal: []

This policy will find all SQL servers allowing traffic from 1.2.2.128/25 CIDR.

.. code-block:: yaml

    policies:
      - name: find-sqlserver-allowing-subnet
        resource: azure.sqlserver
        filters:
          - type: firewall-rules
            include: ['1.2.2.128/25']
