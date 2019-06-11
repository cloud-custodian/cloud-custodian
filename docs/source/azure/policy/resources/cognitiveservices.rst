.. _azure_cognitiveservices:

Cognitive Services
==================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `CognitiveServicesAccount <https://docs.microsoft.com/en-us/python/api/azure.mgmt.cognitiveservices.models.cognitiveservicesaccount?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Cognitive Services Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftcognitiveservicesaccounts/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will find all Cognitive Service accounts with 1000 or more total errors over the 72 hours

.. code-block:: yaml

    policies:
      - name: cogserv-many-failures
        resource: azure.cognitiveservice
        filters:
          - type: metric
            metric: TotalErrors
            op: ge
            aggregation: total
            threshold: 1000
            timeframe: 72
