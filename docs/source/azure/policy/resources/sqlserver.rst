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
- Firewall Rules Filter (see :ref:`azure_filters`)

  .. c7n-schema:: SqlServerFirewallRulesFilter
       :module: c7n_azure.resources.sqlserver

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all SQL servers for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-sql-servers-for-deletion
        resource: azure.sqlserver
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
      - name: delete-test-sqlservers
        resource: azure.sqlserver
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all SQL servers with average DTU consumption under 10 percent over the last 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-sqlserver-under-utilized
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
        actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Under-utilized SQL Server
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename

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
