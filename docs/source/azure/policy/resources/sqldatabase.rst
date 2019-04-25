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
- Short Term Backup Retention Policy Filter
    - Filter on the retention period (in days) of the database's short term backup retention policy.
    - If there is no short term backup retention policy set on the database, it is treated as if the retention is zero days.
    - more info on `Short Term Backups <https://docs.microsoft.com/en-us/azure/sql-database/sql-database-automated-backups>`_
- Long Term Backup Retention Policy Filter
    - Filter on the retention period of the database's long term backup retention policy.
    - `backup-type`: There are 3 types of backups `weekly`, `monthly`, and `yearly`.
    - `retention-period` and `retention-period-units`: The retention period length and units. There are 4 possible units: `days`, `weeks`, `months`, and `years`
    - If the specified backup type has not been set on the resource, it is treated as if the retention is zero days.
    - more info on `Long Term Backups <https://docs.microsoft.com/en-us/azure/sql-database/sql-database-long-term-retention>`_

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

- :ref:`azure_examples_sqldatabasewithpremiumsku`
- :ref:`azure_examples_sqldatabaseshorttermbackupretention`
- :ref:`azure_examples_sqldatabaselongtermbackupretention`
