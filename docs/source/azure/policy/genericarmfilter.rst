.. _azure_genericarmfilter:

Generic Filters
================


``MetricFilter``
Filters Azure resources based on live metrics from the Azure monitor.

.. c7n-schema:: MetricFilter
    :module: c7n_azure.filters


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


``TagActionFilter``
Filters Azure resources based on previously scheduled operations via tags

.. c7n-schema:: TagActionFilter
    :module: c7n_azure.filters


Example Policies
----------------

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

Find VMs that have been marked for stopping tomorrow and notify email address

.. code-block:: yaml

    policies
      - name: find-vms-to-stop
        resource: azure.vm
        filters:
          - type: marked-for-op
            skew: 1
            op: stop
        actions:
          - type: notify
            template: default
            subject: VMs Scheduled To Stop
            to: user@domain.com
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