.. _azure_datalake:

Data Lake
=========

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Profile <https://docs.microsoft.com/en-us/python/api/azure-mgmt-cdn/azure.mgmt.cdn.models.profile?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - MetricFilter - Filter on metrics from Azure Monitor - (see `Datalake Store Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdatalakestoreaccounts/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will find all Datalake Stores with one million or more write requests in the last 72 hours

.. code-block:: yaml

    policies:
      - name: notify-datalake-busy
        resource: azure.datalake
        filters:
          - type: metric
            metric: WriteRequests
            op: ge
            aggregation: total
            threshold: 1000000
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Busy Datalake Stores
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
