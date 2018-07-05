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

This set of policies will mark all IoT Hubs for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-iothubs-for-deletion
        resource: azure.iothub
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
      - name: delete-test-iothubs
        resource: azure.iothub
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all IoT Hubs with 1000 or more dropped messages over the last 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-iothubs-dropping-messages
        resource: azure.iothub
        filters:
          - type: metric
            metric: d2c.telemetry.egress.dropped
            op: ge
            aggregation: total
            threshold: 1000
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: IOT Hubs Dropping Messages
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
