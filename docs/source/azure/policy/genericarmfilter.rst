.. _azure_genericarmfilter:

Generic Filters
================

These filters can be applied to a specific resource type, such as ``azure.vm``, or they can be
applied to all Azure resources by using ``azure.armresource`` as the resource type.

Metric Filter
-------------

``MetricFilter``
Filters Azure resources based on live metrics from the Azure monitor.

.. c7n-schema:: MetricFilter
    :module: c7n_azure.filters

Metrics for Custodian-supported Azure resources:

- `Cognitive Services <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftcognitiveservicesaccounts>`_
- `Cosmos DB <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdocumentdbdatabaseaccounts>`_
- `Data Factory <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdatafactoryfactories>`_
- `IoT Hub <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdevicesiothubs>`_
- `Key Vault <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftkeyvaultvaults>`_
- `Load Balancer <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftnetworkloadbalancers>`_
- `Public IP Address <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftnetworkpublicipaddresses>`_
- `SQL Server Databases <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftsqlserversdatabases>`_
- `Storage Accounts <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftstoragestorageaccounts>`_
- `Virtual Machine <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftcomputevirtualmachines>`_
- `Web Apps (excluding functions) <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftwebsites-excluding-functions>`_

Click `here <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics/>`_
for a full list of metrics supported by Azure resources.


Example Policies
~~~~~~~~~~~~~~~~

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

Find SQL servers with less than 10% average DTU consumption across all databases over last 24 hours

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
            filter:  "DatabaseResourceId eq '*'"


Tag Filter
----------

The "tag filter" is implicitly just the ValueFilter (see :ref:`filters`).
It can be used to filter resources on the presence, absence or value of a tag.

.. c7n-schema:: ValueFilter
    :module: c7n.filters.core


Example Policies
~~~~~~~~~~~~~~~~

This policy will delete all ARM resources with the tag 'Tag1' present

.. code-block:: yaml

    policies
      - name: delete-resources-with-Tag1
        resource: azure.armresource
        filters:
          - tag:Tag1: present
        actions:
          - type: delete

This policy will find all VMs with the tag 'Tag1' absent

.. code-block:: yaml

    policies
      - name: find-vms-without-Tag1
        resource: azure.vm
        filters:
          - tag:Tag1: absent

This policy will find all CosmosDBs with the tag 'Tag1' and value 'Value1'

.. code-block:: yaml

    policies
      - name: find-cosmosdb-tag-value
        resource: azure.cosmosdb
        filters:
          - tag:Tag1: Value1

Marked-For-Op Filter
--------------------

``TagActionFilter``
Filters Azure resources based on previously scheduled operations via tags.

.. c7n-schema:: TagActionFilter
    :module: c7n_azure.filters


Example Policies
~~~~~~~~~~~~~~~~

Find VMs that have been marked for stopping and stop them

.. code-block:: yaml

    policies
      - name: find-vms-to-stop
        resource: azure.vm
        filters:
          - type: marked-for-op
            op: stop
        actions:
          - type: stop

Find VMs that have been marked for stopping tomorrow and notify user@domain.com

.. code-block:: yaml

    policies
      - name: find-vms-to-stop
        resource: azure.vm
        filters:
          - type: marked-for-op
            # 'Fast-forward' 1 day into future. skew_hours is used for hour increments
            skew: 1
            op: stop
        actions:
          - type: notify
            template: default
            subject: VMs Scheduled To Stop
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/test

Cancel operation on resource marked for operation

.. code-block:: yaml

    policies
      - name: find-vms-to-stop
        resource: azure.resourcegroup
        filters:
          - type: marked-for-op
            op: delete
            # custodian_status is default tag, but can be configured
            tag: custodian_status
        actions:
          - type: untag
            tags: ['custodian_status']

Diagnostic Settings Filter
--------------------------

``DiagnosticSettingsFilter``
The diagnostic settings filter is implicitly just the ValueFilter (see :ref:`filters`) on the diagnostic settings for
an azure resource.

.. c7n-schema:: DiagnosticSettingsFilter
    :module: c7n_azure.filters


Example Policies
~~~~~~~~~~~~~~~~

Find Load Balancers that have logs for both LoadBalancerProbeHealthStatus category and LoadBalancerAlertEvent category enabled.
The use of value_type: swap is important for these examples because it swaps the value and the evaluated key so that it evaluates the value provided is in the logs.

.. code-block:: yaml

    policies
      - name: find-load-balancers-with-logs-enabled
        resource: azure.loadbalancer
        filters:
          - type: diagnostic-settings
            key: logs[?category == 'LoadBalancerProbeHealthStatus'][].enabled
            value: True
            op: in
            value_type: swap
          - type: diagnostic-settings
            key: logs[?category == 'LoadBalancerAlertEvent'][].enabled
            value: True
            op: in
            value_type: swap

Find KeyVaults that have logs enabled for the AuditEvent category.

.. code-block:: yaml

    policies
      - name: find-keyvaults-with-logs-enabled
        resource: azure.keyvault
        filters:
          - type: diagnostic-settings
            key: logs[?category == 'AuditEvent'][].enabled
            value: True
            op: in
            value_type: swap