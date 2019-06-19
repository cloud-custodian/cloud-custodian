.. _azure_datafactory:

Data Factory
============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Vault <https://docs.microsoft.com/en-us/python/api/azure.mgmt.keyvault.models.vault?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Data Factory Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdatafactoryfactories/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will find all Data Factories with 10 or more failures in pipeline runs over the last 72 hours

.. code-block:: yaml

    policies:
      - name: datafactory-dropping-messages
        resource: azure.datafactory
        filters:
          - type: metric
            metric: PipelineFailedRuns
            op: ge
            aggregation: total
            threshold: 10
            timeframe: 72
