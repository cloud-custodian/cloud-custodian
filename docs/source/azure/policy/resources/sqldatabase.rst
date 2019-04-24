.. _azure_sqldatabase:

SQL Database
============

the `azure.sqldatabase` resource is a child resource of the :ref:`azure_sqlserver`
resource, and the SQL Server parent id is available as the `c7n:parent-id` property.

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Database <https://docs.microsoft.com/en-us/python/api/azure-mgmt-sql/azure.mgmt.sql.models.database.database?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `SQL Server Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftsqlservers/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

- :ref:`azure_examples_sqldatabasewithpremiumsku`
