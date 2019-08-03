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

- ``short-term-backup-retention``
    - Filter on the retention period (in days) of the database's short term backup retention policy.
    - more info on `Short Term Backups <https://docs.microsoft.com/en-us/azure/sql-database/sql-database-automated-backups>`_
    - If there is no short term backup retention policy set on the database, it is treated as if the retention is zero days.
    - The default comparison operation is `eq`

    .. c7n-schema:: azure.sqldatabase.filters.short-term-backup-retention-policy


- ``long-term-backup-retention``
    - Filter on the retention period of the database's long term backup retention policy.
    - more info on `Long Term Backups <https://docs.microsoft.com/en-us/azure/sql-database/sql-database-long-term-retention>`_
    - If the specified backup type has not been set on the resource, it is treated as if the retention period is zero.
    - The default comparison operation is `eq`
    - The `azure.sqldatabase` resource will only get through the filter if the `retention-period-units` field matches the units specified in the actual long term backup retention policy.
        - Example: if the filter is looking for backups less than 1 year, and the retention policy is set to 6 months, then the database will not get through the filter because there is a unit mismatch.

    .. c7n-schema:: azure.sqldatabase.filters.long-term-backup-retention-policy


Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

- ``update-short-term-backup-retention``
    - Update the retention period (in days) for a database's short term backup retention policy.

    .. c7n-schema:: azure.sqldatabase.actions.update-short-term-backup-retention-policy

- ``update-long-term-backup-retention``
    - Update the retention period for a database's long term backup retention policy.

    .. c7n-schema:: azure.sqldatabase.actions.update-long-term-backup-retention-policy

Example Policies
----------------

- :ref:`azure_examples_sqldatabasewithpremiumsku`
- :ref:`azure_examples_sqldatabasebackupretention`
- :ref:`azure_examples_sqldatabaseupdateretentionpolicies`
