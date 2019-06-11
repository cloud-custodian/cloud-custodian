.. _azure_iothub:

IoT Hub
=======

Filters
-------
- Standard Value Filter (see :ref:`filters`)
    - Model: `IotHubDescription <https://docs.microsoft.com/en-us/python/api/azure.mgmt.iothub.models.iothubdescription?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - MetricFilter - Filter on metrics from Azure Monitor - (see `IoT Hub Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftdevicesiothubs/>`_)
    - Tag Filter - Filter on tags for actions previously applied to resource
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will find all IoT Hubs with 1000 or more dropped messages over the last 72 hours

.. code-block:: yaml

    policies:
      - name: iothubs-dropping-messages
        resource: azure.iothub
        filters:
          - type: metric
            metric: d2c.telemetry.egress.dropped
            op: ge
            aggregation: total
            threshold: 1000
            timeframe: 72
