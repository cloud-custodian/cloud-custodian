.. _azure_genericarmfilter:

Generic Filters
================


``MetricFilter``
Filters Azure resources based on live metrics from the Azure monitor.
.. c7n-schema:: MetricFilter
    :module: c7n_azure.filters

Metrics for Custodian-supported Azure resources:

- `Cognitive Services <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftcognitiveservicesaccounts/>`_
- `Cosmos DB <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdocumentdbdatabaseaccounts/>`_
- `Data Factory <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdatafactoryfactories/>`_
- `IoT Hub <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdevicesiothubs/>`_
- `Key Vault <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftkeyvaultvaults/>`_
- `Load Balancer <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftnetworkloadbalancers/>`_
- `Public IP Address <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftnetworkpublicipaddresses/>`_
- `SQL Server <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftsqlservers/>`_
- `Storage Accounts <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftstoragestorageaccounts/>`_
- `Virtual Machine <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftcomputevirtualmachines/>`_
- `Virtual Network <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftnetworkvirtualnetworkgateways/>`_

Click `here <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics/>`_
for a full list of metrics supported by Azure resources.


Example Policies
-----------------

Find VMs with an average Percentage CPU greater than or equal to 75% over the last 12 hours

.. code-block:: yaml

    policies:
      - name: find-busy-vms
        resource: azure.vm
        filters:
          - type: metric
            metric: Percentage CPU
            aggregation: average
            op: ge
            threshold: 75
            timeframe: 12

Find KeyVaults with more than 1000 API hits in the last hour

.. code-block:: yaml

    policies:
      - name: keyvault-hits
        resource: azure.keyvault
        filters:
          - type: metric
            metric: ServiceApiHit
            aggregation: total
            op: gt
            threshold: 1000
            timeframe: 1

Find SQL servers with less than 10% average DTU consumption over last 24 hours

.. code-block:: yaml

    policies:
      - name: dtu-consumption
        resource: azure.sqlserver
        filters:
          - type: metric
            metric: dtu_consumption_percent
            aggregation: average
            op: lt
            threshold: 10
            timeframe: 24
