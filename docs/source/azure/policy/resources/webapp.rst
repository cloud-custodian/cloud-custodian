.. _azure_webapp:

Web Applications
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Site <https://docs.microsoft.com/en-us/python/api/azure.mgmt.web.models.site?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Web App Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftwebsites-excluding-functions/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will find all web apps with 10 or less requests over the last 72 hours

.. code-block:: yaml

    policies:
      - name: webapp-dropping-messages
        resource: azure.webapp
        filters:
          - type: metric
            metric: Requests
            op: le
            aggregation: total
            threshold: 10
            timeframe: 72
         actions:
          - type: mark-for-op
            op: delete
            days: 7

This policy will find all web apps with 1000 or more server errors over the last 72 hours

.. code-block:: yaml

    policies:
      - name: webapp-high-error-count
        resource: azure.webapp
        filters:
          - type: metric
            metric: Http5xxx
            op: ge
            aggregation: total
            threshold: 1000
            timeframe: 72
